# video-rolling-shutter

## 题面

给手机素材加果冻效应校正后，边缘出现鬼影、运动还更歪了：行时间用固定值，不随高度变；位移与时间平方成正比，动态错乱；重采样越界回绕，边缘出现鬼影；反向位移符号没取反，校正后更歪；多帧估计用均值，滚动量偏小；合成量不钳制，超过 1 后翻卷；行数不符不报错，越界；NaN 位移不校验，整帧变黑；批量共用位移表，帧之间串；`readout_ms=0` 不校验，除零。shutter/warp.py 是核心，tests/test_warp.py 15个红。要修的是：让行时间随高度线性分布、位移与行时间成正比、越界按 `wrap` 回绕或补边、反向位移取反、多帧取最大滚动量、合成量钳制、校验行数与 NaN 位移、批量为每帧使用独立位移表并在失败时整体回滚、校验 `readout_ms > 0` 以避免除零。

## 运行方式

在仓库根目录运行：

```powershell
python -m pytest tests -q
```

初始状态应恰好看到 15 条失败，且没有 collection error、import error、syntax error 或 `errors`：

```text
15 failed in 0.08s
```

所有测试都会调用 `shutter/warp.py` 中的桩函数；实现完成前，每条测试都以 `NotImplementedError` 失败。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 音视频处理 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 测试基线

`tests/test_warp.py` 是判分基线，不得修改；需要实现的只有 `shutter/warp.py`。测试只使用标准库与 pytest，离线运行，不使用随机数。
