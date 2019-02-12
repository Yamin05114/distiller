1. prunner: 所有裁剪的纯虚类

2. level_prunner: 按照比例裁剪

3. magnitude_prunner: 按照标注差大小裁剪，比较简单

4. sensitivity_prunner: 基本上和magnitude一样，但是增加了一个sensitivity的因子，至于怎么得到的现在还不明确。这篇论文做法一定程度造成裁失误.2015提出,2016年宋寒还提出了针对稀疏矩阵的硬件.

5. splicing_prunner: 裁剪拼接：其实就是裁剪不要直接乘以weights，而是保留mask，每次生成新的mask都试试裁剪的model来更新所有weights。走的是裁剪更新weights，裁剪更新weights的流派
