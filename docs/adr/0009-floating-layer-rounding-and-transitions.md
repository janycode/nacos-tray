# 浮层圆角化与入场过渡

## Status

accepted

## Context

当前所有「点击后出现」的界面都是直角 `Toplevel` 硬切出现，无过渡：

- 托盘双栏弹窗：`ServiceListPopup`（`main.py:2012`），每次右击新建并构建全部行（`main.py:2891`）。
- 自定义上下文菜单：`_open_items_menu`（`main.py:4350`），每次调用新建 `Toplevel`。
- 工具提示：`main.py:4182`，延迟 400ms 后硬切。
- 自绘气泡：已有 16ms 步进的淡入/淡出（`notifier.py:442`、`notifier.py:457`），可复用其做法。

tkinter 没有补间引擎，过渡只能用 `after(16ms)` 手写；`-alpha` 在 Windows 上对 `Toplevel` 有效。

需求明确要求：**点击唤出菜单 / 弹窗 / 界面的效果要丝滑、要快**。

## Decision

1. **圆角**：浮层用 `-transparentcolor` 抠一个专用色，再用 Canvas 画圆角矩形（复用 `notifier._round_rect` 的思路，抽到 `theme.py` 作为公共绘制函数）。圆角半径：托盘弹窗 16、自定义菜单 12、工具提示 10、气泡维持 12。
2. **过渡参数集中**在 `theme.py`，单位毫秒：`MENU_FADE_MS = 120`、`POPUP_FADE_MS = 140`、`TOOLTIP_DELAY_MS = 200`、`TOOLTIP_FADE_MS = 100`、`BUBBLE_FADE_MS = 150`。所有缓动统一 ease-out cubic。
3. **补间助手**：`theme.animate_alpha(window, target, duration_ms)`，内部用 `after(16)` 逐步写 `-alpha`；供各浮层复用，禁止各处散写 `after`。
4. **位移只给托盘弹窗**：从托盘所在屏幕边缘方向轻微滑入 8px，与淡入同步；菜单、工具提示只做淡入，避免"飞来飞去"。
5. **尊重系统减少动画**：启动时读 `SystemParametersInfo(SPI_GETCLIENTAREAANIMATION)`，为假时所有过渡时长直接归零（瞬时出现），只保留圆角等静态特征。
6. **不打断**：轮询数据到达、来源切换、主题切换时不重启正在播放的过渡；动画结束前不重复触发动画。

## Considered Options

- **用 `wm_geometry` 每帧移动整个窗口做滑动**：与 `-alpha` 同样是 `after` 驱动，但位移比淡入更容易暴露抖动和边框残影，收益低。
- **引入带动画的第三方库**：违背零依赖。
- **只改气泡，不动菜单/弹窗**：气泡已在 `notifier.py` 有淡入，需求的核心痛点是每次右击新建的托盘弹窗与菜单，改动面太小不得要领。

## Consequences

- shaped window（`overrideredirect` + `-transparentcolor`）的焦点行为需要重新验证：现有的 `<FocusOut>` 收起逻辑（`main.py:4385`、`main.py:2415`）在新窗口上必须仍然可靠，否则会出现"点任意处关不掉"。
- 透明色必须与当前主题任何表面色都不同，主题切换时需同步更新透明色（`notifier.py:35` 的 `_TRANSPARENT_KEY` 现为固定值，需要纳入主题管理或在切换时重建浮层）。
- 圆角化后浮层的命中区域以画布为准，四个角点击不应触发收起；需要明确"点击外部收起"的判定边界。
- 与 ADR-0010 的单例复用是同一批改动，需一起验证，避免"复用单例 + 透明色"互相踩踏。
