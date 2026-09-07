# Background operation

The browser is a client. The Python process runs jobs and folder monitoring.
Closing a tab leaves that process running. Closing the terminal stops a foreground process.
A per-user service separates the worker from the terminal and starts it at user login.

## Enable a service

Run setup. Start the normal app and create a vault passphrase.
Enable the required folder monitor or LocalFlow trigger. Its configuration is stored in the vault.
Stop the foreground process. Run `run.py service --install` with the virtual-environment Python.
Enter the same vault passphrase. The command saves it in a supported secure OS credential store.
The worker starts with `worker --keyring --no-browser`. The passphrase is not placed in arguments or service files.

| OS | Service | Credential store |
| :--- | :--- | :--- |
| Windows | Current-user scheduled task, interactive token, least privilege | Windows credential store |
| macOS | User LaunchAgent | Keychain |
| Linux | systemd user service | Secret Service or KWallet |

This is a user-login service, not a machine-wide boot service. The computer must be awake.
The OS credential store must be available and unlocked. Do not configure a plaintext keyring backend.
No service launches mouse or keyboard actions. Those require a separate interactive run and confirmation.

## Stop or remove

Use the app's Stop control to disable monitoring. The disabled state remains disabled after restart.
Use `run.py service --remove` to stop and remove this app service and delete its saved credential.
The command refuses to remove a service definition that does not match this app and data directory.
Keep the project and .venv at the installed path. Reinstall the service after moving them.

Native service installation needs a real OS user session. Configuration tests are not evidence of a completed installation on every OS.
