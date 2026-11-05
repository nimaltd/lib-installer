# lib-installer is now libNIMA

lib-installer is now [libNIMA](https://github.com/nimaltd/libNIMA): the same installer, rewritten in Rust, with a window beside the command line, the same on Windows, macOS and Linux. It installs embedded C libraries into STM32, Zephyr, ESP-IDF, Arduino and PlatformIO projects, and needs no Python.

Download it from [its releases page](https://github.com/nimaltd/libNIMA/releases/latest), then take this one out:

```bash
pip uninstall lib-installer
libnima owner/example
```

**The commands are the same**, with `libnima` in front: `lib-installer owner/example --dir Libs/example` is `libnima owner/example --dir Libs/example`.

**Your projects move over by themselves.** A project lib-installer installed into moves over on the first run: `.lib-installer.json` becomes `.libnima.json`, and the lines that mark its blocks in your files name libnima. Each file is saved first, as a `.bak`.

**Your libraries install as they are.** libNIMA reads an `installer.yml` written for lib-installer 3.x or 4.x through a built-in converter, and `libnima --convert` writes it out as a `libnima.yml`. A step written as a Python script needs Python on that machine.

This last release, 5.0.0, only says this, and installs nothing. 4.0.1 was the last that installed, and its code stays in this repository's history.

---

## Support

I write these tools and libraries in my own time and give them away, because good tools should be easy to get. If this one saved you an afternoon, there are two things that genuinely help:

**Star [libNIMA](https://github.com/nimaltd/libNIMA).** It costs you one click, it helps other engineers find the tool, and it is the main reason I keep going.

**[Buy me a coffee on Ko-fi](https://ko-fi.com/nimaltd).** Any amount is a real motivation to keep writing, documenting and maintaining this work.

---

## License

Apache License 2.0. See [LICENSE](https://github.com/nimaltd/lib-installer/blob/main/LICENSE).
