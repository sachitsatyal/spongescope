# Colab: cluster lncRNAs with MMseqs2 (one-time, step 2.3)

1. Open https://colab.research.google.com -> New notebook.
2. Left sidebar -> Files (folder icon) -> upload
   `data/interim/clustering/lncrna_representatives.fa` from the project.
3. Paste this into a cell and run it:

```bash
%%bash
wget -q https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz
tar xzf mmseqs-linux-avx2.tar.gz
export PATH=$(pwd)/mmseqs/bin:$PATH
mmseqs version
mmseqs easy-cluster lncrna_representatives.fa lnc tmp \
    --min-seq-id 0.8 -c 0.5 --cov-mode 1 --dbtype 2 --threads 4 > mmseqs.log 2>&1
tail -3 mmseqs.log
echo "genes:";    wc -l < lnc_cluster.tsv
echo "clusters:"; cut -f1 lnc_cluster.tsv | sort -u | wc -l
```

4. In the Files panel, refresh, then download `lnc_cluster.tsv`.
5. Save it in the project as `data/interim/clustering/lnc_cluster.tsv`.

Expected: genes = 1313; clusters a bit below that (most lncRNAs are unique).

If `easy-cluster` errors on nucleotides, replace `easy-cluster` with `easy-linclust`
(same arguments) and rerun.

Settings: two lncRNAs share a cluster if they are >=80% identical over >=50% of the
target. Every gene in a cluster lands in the same split, so near-duplicate lncRNAs
cannot sit on both sides of train/test.
