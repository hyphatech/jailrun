---
icon: material/download-box-outline
---

# Installation

Jailrun runs on macOS (Apple Silicon and Intel), Linux (x86_64 and aarch64), and FreeBSD (x86_64 and aarch64).
On macOS, Homebrew handles all dependencies automatically. On Linux and FreeBSD, install the system dependencies first.

!!! note "Virtualization"

    Jailrun uses [QEMU](https://www.qemu.org/) to run a FreeBSD virtual machine on your host. QEMU provides hardware-accelerated virtualisation via HVF on macOS, KVM on Linux, and TCG emulation on FreeBSD.

=== ":fontawesome-brands-apple: macOS"

    Install via Homebrew:

    ```bash
    brew tap hyphatech/jailrun
    brew install jailrun
    ```

    This installs `jrun` and all its dependencies — Python, QEMU, Ansible, and mkisofs.

=== ":fontawesome-brands-linux: Linux"

    Install system dependencies:

    ```bash
    # Debian/Ubuntu
    sudo apt install qemu-system mkisofs ansible

    # Fedora
    sudo dnf install qemu-system-x86 genisoimage ansible

    # Arch
    sudo pacman -S qemu-full cdrtools ansible
    ```

    Install Python 3.13+ using your operating system's package manager or preferred installation method.

    Install [uv](https://docs.astral.sh/uv/) using your distribution's package manager if available, or via the official installer:

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    Then install `jrun`:

    ```bash
    uv tool install jailrun
    ```

=== ":fontawesome-brands-freebsd: FreeBSD"

    Install system dependencies:

    ```bash
    pkg install qemu edk2-qemu-x64 uv rust cdrtools python313
    ```

    Some Python dependencies may not have prebuilt wheels on FreeBSD and may need to be compiled locally, so `rust` is required.

    Install Ansible and `jrun` with Python 3.13:

    ```bash
    uv tool install --python 3.13 --with-executables-from ansible-core ansible
    uv tool install --python 3.13 jailrun
    ```

    !!! tip

        If `jrun` is not found after installation, make sure uv's user bin directory is on your PATH:

        ```bash
        export PATH="$HOME/.local/bin:$PATH"
        ```

!!! tip

    To install `jrun` directly from the latest source:

    ```bash
    uv tool install "git+https://github.com/hyphatech/jailrun.git@main"
    ```
