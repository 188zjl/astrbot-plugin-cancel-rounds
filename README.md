# astrbot-plugin-cancel-rounds

AstrBot 通用插件：删除当前会话最近几轮聊天记录。

这里的“1 轮”定义为：

- 1 次用户提问
- 1 次助手回答

也就是常说的 `1 问 1 答`。

## 默认命令

- `/cancel`

## 自定义命令

可以通过配置项 `custom_commands` 增加额外命令别名，例如：

```text
撤回轮次,删除轮次
```

注意：

- 固定主命令是 `/cancel`
- `custom_commands` 属于额外消息入口
- 这些别名不一定会出现在平台 slash 自动补全里

## 使用方式

```text
/cancel
/cancel 2
```

含义：

- `/cancel`：默认删除最近 1 轮
- `/cancel 2`：删除最近 2 轮

如果填写的数字大于当前会话实际轮数，插件会尽量删到空。

## 上下文同步

插件会先删除 AstrBot 当前会话历史。

如果环境里同时安装了兼容的长期记忆插件，例如 `LivingMemory`，插件还会尝试同步回滚对应的最近消息和相关记忆，避免出现“聊天删了但记忆还在”的情况。

## 配置项

见 [`_conf_schema.json`](./_conf_schema.json)。

当前提供：

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
├── main.py
├── metadata.yaml
└── _conf_schema.json
```

## 许可

MIT
