# R0 Blind Annotation Pack

版本：v0.1
状态：`SUPERSEDED / DO NOT ANNOTATE`
日期：2026-07-15

> 维护者已重开 v0.1 六例选择。本包基于过窄的 5 张源图，不得继续填写；请先完成 `data/local/text-seeded-container-association/r0-candidate-review-v0.2/FORM.md`。最终六例确定后会生成新的 A/B 盲标包。

## 目的

本包用于六个 R0 ROI 的双人独立人工标注，冻结文字组、容器归属、可见边界、虚拟边界、无容器文字支持区域和人工不确定区域。

本包不是 benchmark manifest，不包含算法输出、旧 Cleaning mask、预期答案、阈值或评价结果，也不用于实际 Cleaning。

## 包内容

```text
r0-blind/
  README.md
  INSTRUCTIONS.md
  images/
    case-01.png ... case-06.png
  annotator-a/
    FORM.md
    overlays/
  annotator-b/
    FORM.md
    overlays/
  coordinator/
    CASE-KEY.md
    ADJUDICATION.md
```

六张 `case-XX.png` 都是冻结 ROI 的原始分辨率裁剪，没有缩放。坐标原点为左上角，`x` 向右、`y` 向下。

## 角色隔离

- Annotator A 阅读 `INSTRUCTIONS.md`，填写 `annotator-a/FORM.md`，叠加图保存到 `annotator-a/overlays/`。
- Annotator B 阅读相同说明，填写 `annotator-b/FORM.md`，叠加图保存到 `annotator-b/overlays/`。
- 两人在各自提交完成前不得查看对方表单或叠加图。
- 两名标注者都不要打开 `coordinator/`，也不要为了寻找“正确答案”查看 Spike 的冻结语义、算法输出或旧报告。
- Coordinator 只在 A/B 都提交后打开 `coordinator/CASE-KEY.md` 和 `coordinator/ADJUDICATION.md`。

一个人填写 A、隔一段时间再填写 B，不算双人独立标注。

## 开始方式

1. 先完整阅读 [INSTRUCTIONS.md](INSTRUCTIONS.md)。
2. 确定自己是 A 或 B，只进入对应目录。
3. 对每个 case 先复制原图，再在副本上画线；不得覆盖 `images/` 中的原图。
4. 每完成一张叠加图，立即填写对应 case 的表单。
5. 六个 case 全部完成后，记录完成时间并停止修改。

如果证据不足，直接标为 `UNCERTAIN`。本任务不奖励猜测或覆盖率。
