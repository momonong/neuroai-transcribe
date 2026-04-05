# Pipeline case compare：`test` vs `test1`

## 狀態

- `test`: OK
- `test1`: OK

## 指標總覽（以終稿 transcript.json 為準；若有 GT 則包含 CER）

| **指標** | **test** | **test1** | **Δ (test1-test)** |
| --- | --- | --- | --- |
| **GT 基準字數（正規化）** | 7326 | 7326 | — |
| **終稿字數（正規化）** | 6836 | 6991 | +155 |
| **CER** | 0.230003 | 0.218673 | -0.01133 |
| **Ins/Del/Sub** | 252/742/691 | 278/613/711 | — |
| **遺失 aligned segment id（終稿）** | 0 | 0 | +0 |
| **chunk 數** | 4 | 4 | — |
| **Whisper 覆蓋率平均** | 79.71% | 80.33% | +0.006175 |
| **Aligned Unknown ratio 平均** | 0.89% | 0.99% | +0.00105 |

## 分 chunk 對照（終稿/aligned 字元比、missing id、Unknown）

| **Chunk** | **test retention** | **test1 retention** | **test missing** | **test1 missing** | **test Unknown** | **test1 Unknown** |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | 100.00% | 100.00% | 0 | 0 | 0.68% | 0.80% |
| **2** | 100.00% | 100.00% | 0 | 0 | 0.29% | 1.14% |
| **3** | 100.00% | 100.00% | 0 | 0 | 1.72% | 1.75% |
| **4** | 100.00% | 100.00% | 0 | 0 | 0.86% | 0.28% |

## 產物路徑提示

- `test`: `data/test/output/transcript.json`、`data/test/intermediate/`
- `test1`: `data/test1/output/transcript.json`、`data/test1/intermediate/`
