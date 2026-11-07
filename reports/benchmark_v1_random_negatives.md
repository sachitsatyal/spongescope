# SpongeScope benchmark (cold-start splits)

AUROC / AUPR with 95% CI from a lncRNA-level bootstrap. `lift` = AUPR / positive rate.
`per-lnc AUROC` = mean AUROC within each lncRNA (ignores length/hub shortcuts).

## test_cold_lncrna  (pos 1,455 / neg 13,711, positive rate 0.096)

| model | AUROC | AUPR | lift | per-lnc AUROC | ECE |
|---|---|---|---|---|---|
| gbm_all | 0.895 [0.874-0.913] | 0.442 [0.385-0.498] | 4.61 | 0.893 | 0.010 |
| seed_match | 0.882 [0.860-0.904] | 0.432 [0.376-0.491] | 4.50 | 0.887 | 0.029 |
| mirna_popularity | 0.601 [0.566-0.634] | 0.131 [0.112-0.155] | 1.37 | 0.532 | 0.013 |
| lncmirpath | 0.542 [0.515-0.569] | 0.109 [0.098-0.121] | 1.14 | 0.528 | 0.019 |
| length_only | 0.507 [0.494-0.526] | 0.097 [0.091-0.109] | 1.01 | 0.500 | 0.018 |

## test_cold_both  (pos 140 / neg 1,436, positive rate 0.089)

| model | AUROC | AUPR | lift | per-lnc AUROC | ECE |
|---|---|---|---|---|---|
| gbm_all | 0.903 [0.870-0.931] | 0.469 [0.359-0.581] | 5.28 | 0.878 | 0.057 |
| seed_match | 0.889 [0.853-0.922] | 0.456 [0.349-0.574] | 5.14 | 0.900 | 0.036 |
| length_only | 0.548 [0.464-0.625] | 0.105 [0.071-0.152] | 1.18 | 0.500 | 0.020 |
| lncmirpath | 0.525 [0.471-0.579] | 0.092 [0.069-0.122] | 1.03 | 0.529 | 0.021 |
| mirna_popularity | 0.500 [0.500-0.500] | 0.089 [0.066-0.112] | 1.00 | 0.500 | 0.080 |

## val  (pos 1,418 / neg 10,375, positive rate 0.120)

| model | AUROC | AUPR | lift | per-lnc AUROC | ECE |
|---|---|---|---|---|---|
| seed_match | 0.891 [0.844-0.921] | 0.512 [0.383-0.646] | 4.26 | 0.892 | 0.032 |
| gbm_all | 0.894 [0.874-0.920] | 0.481 [0.431-0.549] | 4.00 | 0.896 | 0.038 |
| length_only | 0.631 [0.496-0.754] | 0.314 [0.090-0.504] | 2.61 | 0.500 | 0.012 |
| mirna_popularity | 0.575 [0.542-0.621] | 0.142 [0.101-0.203] | 1.18 | 0.495 | 0.015 |
| lncmirpath | 0.518 [0.487-0.548] | 0.131 [0.091-0.192] | 1.09 | 0.483 | 0.005 |
