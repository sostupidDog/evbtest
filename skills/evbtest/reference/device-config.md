# Device Configuration

File: `configs/devices.yaml`

## SSH Connection

```yaml
devices:
  my_server:
    description: "Linux server"
    tags: ["x86"]
    connection:
      type: ssh
      host: 192.168.1.10
      port: 22
      username: root
      password: "secret"            # or: key_filename: ~/.ssh/id_rsa
      timeout: 30.0
    prompt_pattern: "[#\\$]\\s*$"
```

## Serial TCP Connection

```yaml
devices:
  my_board:
    description: "ARM64 board"
    tags: ["arm64"]
    connection:
      type: serial_tcp
      host: 192.168.1.200
      port: 5001
      timeout: 30.0
    prompt_pattern: "[#\\$>]\\s*$"
    uboot_prompt: "=>"
    login_prompt: "login:"
```

## Dual-Channel (SSH + Serial)

Same device accessible via both SSH and serial:

```yaml
devices:
  my_board:
    description: "ARM64 board with dual channel"
    connection:
      type: ssh
      host: 192.168.1.10
      port: 22
      username: root
      password: "secret"
    secondary_connection:
      type: serial_tcp
      host: 192.168.1.200
      port: 5001
    prompt_pattern: "[#\\$>]\\s*$"
```

## Config Fields

| Field | Required | Description |
|-------|----------|-------------|
| `connection.type` | yes | `ssh` or `serial_tcp` |
| `connection.host` | yes | IP or hostname |
| `connection.port` | no | SSH default 22, serial default 5000 |
| `connection.username` | SSH | Login username |
| `connection.password` | no | Password auth (SSH) |
| `connection.key_filename` | no | Key file path (SSH) |
| `connection.timeout` | no | Default 30s |
| `secondary_connection` | no | Second channel config (same format) |
| `prompt_pattern` | no | Regex for shell prompt, default `[#\$>]\s*$` |
| `uboot_prompt` | no | U-Boot prompt, default `=>` |
| `login_prompt` | no | Login prompt, default `login:` |
| `tags` | no | String list for filtering |
| `env` | no | Key-value dict accessible in tests |

## prompt_pattern Tips

This regex is used to detect when a command finishes executing. Common prompts:

| Device Prompt | prompt_pattern |
|---------------|----------------|
| `root@board:~# ` | `"[#\\$>]\\s*$"` |
| `[root@board]# ` | `"[#\\$>]\\s*$"` |
| `=> ` (U-Boot) | `"=>\\s*$"` |
| `$ ` (non-root) | `"[$]\\s*$"` |
| `root@localhost:/# ` | `"[#\\$>]\\s*$"` |

ANSI escape sequences in prompts are handled automatically (stripped before matching).
