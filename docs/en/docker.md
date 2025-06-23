# 🐳 Docker and Docker Compose - Installation Guide

![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-A81D33?style=for-the-badge&logo=debian&logoColor=white)

Comprehensive guide for installing Docker and Docker Compose on Ubuntu 24 and Debian 12 operating systems.

## 📋 Table of Contents

- [Requirements](#-requirements)
- [Installation](#-installation)
- [Installation Verification](#-installation-verification)

## 🔧 Requirements

### Supported Operating Systems:

- **Ubuntu 24 (Noble Numbat)**
- **Debian 12 (Bookworm)**

### System Requirements:

- 64-bit architecture (amd64)
- Administrator privileges (sudo)
- Active internet connection

## 🚀 Installation

### Step 1: Install Required Packages

First, install additional packages needed for working with repositories:

```bash
sudo apt install curl wget software-properties-common ca-certificates apt-transport-https -y
```

### Step 2: Import Docker GPG Key

Import the official Docker GPG key for your operating system:

#### 🟠 For Ubuntu:

```bash
wget -O- https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor | sudo tee /etc/apt/keyrings/docker.gpg > /dev/null
```

#### 🔴 For Debian:

```bash
wget -O- https://download.docker.com/linux/debian/gpg | gpg --dearmor | tee /etc/apt/keyrings/docker.gpg > /dev/null
```

### Step 3: Add Docker Repository

Add the official Docker repository to your package sources list:

#### 🟠 For Ubuntu:

```bash
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

#### 🔴 For Debian:

```bash
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### Step 4: Update Package Index

Update the list of available packages:

```bash
sudo apt update
```

### Step 5: Install Docker

Install Docker Community Edition:

```bash
sudo apt install docker-ce -y
```

### Step 6: Install Docker Compose

Install Docker Compose:

```bash
sudo apt install docker-compose -y
```

## ✅ Installation Verification

After completing the installation, verify that everything is working correctly:

### Check Docker Version:

```bash
docker --version
```

### Check Docker Compose Version:

```bash
docker-compose --version
```

### Check Docker Service Status:

```bash
sudo systemctl status docker
```

### Test Container Run:

```bash
sudo docker run hello-world
```