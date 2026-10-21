"""
The core of lib-installer, the same for every platform.

It fetches a library from GitHub, a zip or a folder, reads its installer.yml,
installs what it needs first, copies its files and keeps what the user wrote
between USER CODE markers. What a project looks like, and how a library is
registered with it, comes from the platform through target.use().
"""
