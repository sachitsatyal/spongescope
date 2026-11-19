#!/usr/bin/env nextflow

/*
 * SpongeScope pipeline.
 *
 * Why this exists: every step below already runs as a single `uv run` command, and that is how
 * they are run during development. What a workflow manager adds is that the ORDER and the
 * INPUTS are declared rather than remembered -- a new machine reproduces the run from one
 * command, and a failed step resumes instead of restarting.
 *
 * It does not run on the Windows workstation: Nextflow needs Bash and Java 17+ and is POSIX
 * only. It runs in GitHub Actions (-profile test, a small subset) and on a Kaggle GPU notebook
 * (-profile kaggle, the full run).
 *
 *   nextflow run main.nf -profile test
 *   nextflow run main.nf -profile kaggle
 *   nextflow run main.nf -profile kaggle -resume
 */

nextflow.enable.dsl = 2

params.outdir      = 'results'
params.target      = 'dev'      // dbt target: dev (DuckDB) or prod (Snowflake)
params.max_genes   = 0          // 0 = all; the test profile limits it
params.seeds       = [42]       // training seeds; multirun in the full profile
params.skip_train  = false

process DBT_BUILD {
    tag "target=${params.target}"
    publishDir "${params.outdir}/dbt", mode: 'copy', pattern: 'dbt/target/*.json'

    output:
    path 'warehouse.ok', emit: ready

    script:
    """
    cd ${projectDir}/dbt && dbt build --profiles-dir . --target ${params.target}
    touch ${task.workDir}/warehouse.ok
    """
}

process EMBEDDINGS {
    tag 'RNA-FM'
    label 'gpu'

    input:
    path ready

    output:
    path 'embeddings.ok', emit: ready

    script:
    """
    cd ${projectDir} && python -m spongescope.features.rnafm_embed
    touch ${task.workDir}/embeddings.ok
    """
}

process ACCESSIBILITY {
    tag 'RNAplfold'

    input:
    path ready

    output:
    path 'accessibility.ok', emit: ready

    script:
    """
    cd ${projectDir} && python -m spongescope.features.accessibility
    touch ${task.workDir}/accessibility.ok
    """
}

process SITE_TABLES {
    tag 'candidate sites'

    input:
    path embeddings
    path accessibility

    output:
    path 'sites.ok', emit: ready

    script:
    """
    cd ${projectDir} && python -m spongescope.features.sites
    touch ${task.workDir}/sites.ok
    """
}

process BASELINES {
    tag 'classic + site_gbm'
    publishDir "${params.outdir}/baselines", mode: 'copy'

    input:
    path sites

    output:
    path 'baselines.ok', emit: ready

    script:
    """
    cd ${projectDir} && python -m spongescope.baselines.classic
    cd ${projectDir} && python -m spongescope.baselines.site_gbm
    touch ${task.workDir}/baselines.ok
    """
}

process TRAIN {
    tag "seed=${seed}"
    label 'gpu'
    publishDir "${params.outdir}/train", mode: 'copy'

    input:
    path sites
    each seed

    output:
    path "trained_${seed}.ok", emit: ready

    script:
    """
    cd ${projectDir} && python -m spongescope.train_site seed=${seed} run_name=sitemil_s${seed}
    touch ${task.workDir}/trained_${seed}.ok
    """
}

process REPORT {
    tag 'benchmark'
    publishDir "${params.outdir}", mode: 'copy'

    input:
    path trained

    output:
    path 'benchmark.md', optional: true

    script:
    """
    cd ${projectDir} && python scripts/compare_runs.py
    cp ${projectDir}/reports/benchmark.md ${task.workDir}/ 2>/dev/null || true
    """
}

workflow {
    DBT_BUILD()
    EMBEDDINGS(DBT_BUILD.out.ready)
    ACCESSIBILITY(DBT_BUILD.out.ready)
    SITE_TABLES(EMBEDDINGS.out.ready, ACCESSIBILITY.out.ready)
    BASELINES(SITE_TABLES.out.ready)

    if (!params.skip_train) {
        TRAIN(SITE_TABLES.out.ready, params.seeds)
        REPORT(TRAIN.out.ready.collect())
    }
}

workflow.onComplete {
    log.info """
    ${workflow.success ? 'Completed' : 'FAILED'} in ${workflow.duration}
    Results: ${params.outdir}
    ${workflow.success ? '' : "Resume with: nextflow run main.nf -profile <p> -resume"}
    """.stripIndent()
}
