# Colab: cluster lncRNAs with MMseqs2 (one-time, Phase 2.3)

1. Open https://colab.research.google.com -> New notebook.
2. Left sidebar -> Files -> upload `data/interim/clustering/lncrna_representatives.fa`.
3. Run this cell:

```bash
%%bash
wget -q https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz
tar xzf mmseqs-linux-avx2.tar.gz
export PATH=$(pwd)/mmseqs/bin:$PATH
mmseqs version
mmseqs easy-cluster lncrna_representatives.fa lnc tmp \
    --min-seq-id 0.8 -c 0.5 --cov-mode 1 --dbtype 2 --threads 4
wc -l lnc_cluster.tsv
cut -f1 lnc_cluster.tsv | sort -u | wc -l
```

4. Download `lnc_cluster.tsv` (two columns: cluster representative, member gene ID).
5. Save it as `data/interim/clustering/lnc_cluster.tsv` in the project.

Settings: two lncRNAs share a cluster if they are >=80% identical over >=50% of the
target. All genes in one cluster go to the same split, so near-duplicate lncRNAs
cannot sit on both sides of train/test.
