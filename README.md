# astrbot-plugin-cancel-rounds

AstrBot 通用插件：删除当前会话最近几轮聊天记录。

这里的“1 轮”定义为：

- `1 次用户提问`
- `1 次助手回答`

也就是常说的 `1问1答`。

## 默认命令

- `/cancel`

## 自定义命令

可以通过配置项 `custom_commands` 增加额外别名，例如：

```text
撤回轮次,删除轮次
```

注意：

- 固定主命令 `/cancel` 会正常参与 AstrBot 命令注册
- `custom_commands` 属于额外消息匹配入口
- 这些别名不一定会出现在平台 slash 自动补全中

## 使用方式

```text
/cancel
/cancel 2
```

含义：

- `/cancel`：默认删除最近 1 轮
- `/cancel 2`：删除最近 2 轮

如果你填的数字大于当前会话实际轮数，插件会尽量删到空。

## 配置项

见 [`_conf_schema.json`](./_conf_schema.json)。

当前仅提供：

- `custom_commands`

## 安装

把插件目录放到 AstrBot 插件目录下，例如：

```text
AstrBot/data/plugins/astrbot_plugin_cancel_rounds
```

然后重启 AstrBot。

## 文件结构

```text
astrbot_plugin_cancel_rounds/
├─ main.py
├─ metadata.yaml
└─ _conf_schema.json
```

## 许可证

MIT
