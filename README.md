# MingChaoBQ - 鸣潮表情包插件

> 项目地址：https://github.com/Xbaiyz12/MingChaoBQ

基于 [GsCore](https://github.com/Genshin-bots/gsuid_core) 的鸣潮表情包插件。

## ✨ 功能特性

- 🎲 随机表情 — 从全部表情里随机发一张
- 🎨 按画师/角色/表情名检索 — 画师模糊搜索，角色支持别名，表情精准匹配
- 📋 列表图 — 卡片展示画师和角色，每个角色都有独立图标
- 🖼️ 帮助图 — 基于 GsCore `get_new_help` 渲染
- 🔒 群白名单 — 可开关，只允许指定群使用
- 🌐 API 同步 — 手动/定时从远程 API 拉取表情包，自动按画师/角色归档
- 🎛️ 网页控制台配置 — 所有配置项可在控制台修改，即时生效

## 📦 安装

```bash
cd gsuid_core/plugins
git clone https://github.com/Xbaiyz12/MingChaoBQ.git