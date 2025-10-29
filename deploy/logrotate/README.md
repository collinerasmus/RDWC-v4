# RDWC-v4 Logrotate Configuration

This directory contains logrotate configuration to prevent log-based file descriptor bloat.

## Installation

Copy the logrotate configuration to the system directory:

```bash
sudo cp deploy/logrotate/rdwc /etc/logrotate.d/rdwc
sudo chown root:root /etc/logrotate.d/rdwc
sudo chmod 644 /etc/logrotate.d/rdwc
```

## Configuration Details

- **Rotation**: Weekly rotation with 4 weeks retention
- **Method**: `copytruncate` to avoid disrupting running processes
- **Compression**: Delayed compression to save disk space
- **Permissions**: Files created with `pi:pi` ownership

## Testing

Test the logrotate configuration:

```bash
sudo logrotate -d /etc/logrotate.d/rdwc
```

Force rotation for testing:

```bash
sudo logrotate -f /etc/logrotate.d/rdwc
```