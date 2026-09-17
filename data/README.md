# data/

| 目录 | 策略 |
| --- | --- |
| `raw/` | **只读**。由人工导入脚本写入；agent 与实验脚本一律不得改动（`.omp/hooks/pre/guard-data-write.ts` 拦截）。不入库。 |
| `interim/` | 实验中间产物，可重建，不入库。 |
| `processed/` | 建模用数据集，由 `analysis/` 或实验脚本重建，不入库。 |

## 约定

1. 每个原始数据集在 `raw/` 下建独立子目录，并附 `SOURCE.md`：来源 URL、获取日期、许可证、sha256。
2. 实验只从 `raw/` 读取，绝不写回；需要修正数据时，产出到 `processed/` 并记录变换脚本路径。
3. 切分（train/valid/test）必须落盘为显式文件，禁止在代码里用未固定 seed 的随机切分——切分泄漏是复核重点。
4. 体积超过 100MB 的数据集改为外部存储（对象存储/Zenodo），在 `SOURCE.md` 记录 URL + sha256。
