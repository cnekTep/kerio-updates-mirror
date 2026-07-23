# 🐳 Docker and Docker Compose - Installation Guide

![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-A81D33?style=for-the-badge&logo=debian&logoColor=white)

Comprehensive guide for installing Docker and Docker Compose on Ubuntu and Debian operating systems.
> 📖 This guide is a condensed version of the official Docker installation manual. For the full, always up-to-date
> reference, see [docs.docker.com/engine/install](https://docs.docker.com/engine/install/).

## 📋 Table of Contents

- [Requirements](#-requirements)
- [Uninstall Old Versions](#-uninstall-old-versions)
- [Installation](#-installation)
- [Installation Verification](#-installation-verification)

## 🔧 Requirements

### Supported Operating Systems:

- **Ubuntu 26 (Resolute Raccoon)**
- **Ubuntu 24 (Noble Numbat)**
- **Ubuntu 22 (Jammy Jellyfish)**
- **Debian 13 (Trixie)**
- **Debian 12 (Bookworm)**
- **Debian 11 (Bullseye)**

### System Requirements:

- 64-bit architecture (amd64)
- Administrator privileges (sudo)
- Active internet connection

> ⚠️ **All commands below are shown without `sudo`.** Switch to an elevated shell first and run every command from
> there:
> - **Ubuntu**: `sudo su`
> - **Debian**: log in / switch directly to the `root` user

## 🗑️ Uninstall Old Versions

Before you can install Docker Engine, you need to uninstall any conflicting packages.

Your Linux distribution may provide unofficial Docker packages, which may conflict with the official packages provided
by Docker. You must uninstall these packages before you install the official version of Docker Engine.

```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do apt remove $pkg; done
```

> ℹ️ It's fine if `apt` reports some of these packages as "not installed" - the command simply skips them.

## 🚀 Installation

### Step 1: Install Required Packages

First, install additional packages needed for working with repositories:

```bash
apt install curl ca-certificates -y
```

### Step 2: Add Docker's official GPG key

Import the official Docker GPG key for your operating system:

#### 🟠 For Ubuntu:

```bash
install -m 0755 -d /etc/apt/keyrings
```

```bash
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
```

```bash
chmod a+r /etc/apt/keyrings/docker.asc
```

#### 🔴 For Debian:

```bash
install -m 0755 -d /etc/apt/keyrings
```

```bash
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
```

```bash
chmod a+r /etc/apt/keyrings/docker.asc
```

### Step 3: Add Docker Repository

Add the official Docker repository to your package sources list:

#### 🟠 For Ubuntu:

```bash
tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

#### 🔴 For Debian:

```bash
tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

### Step 4: Update Package Index

Update the list of available packages:

```bash
apt update
```

### Step 5: Install Docker packages

```bash
apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
```

## ✅ Installation Verification

After completing the installation, verify that everything is working correctly:

### Check Docker Version:

```bash
docker --version
```

### Check Docker Compose Version:

```bash
docker compose version
```

### Check Docker Service Status:

```bash
systemctl status docker
```

### Test Container Run:

```bash
docker run hello-world
```

If the command prints a welcome message, Docker is installed and working correctly.

## 📚 Further Reading

For advanced installation options, other Linux distributions, or troubleshooting, refer to the official Docker
documentation: [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)