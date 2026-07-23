<div align="center">

# 🔄 Kerio Updates Mirror

### Local update mirror for Kerio Control and Kerio Connect products

![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=flat&logo=docker&logoColor=white)
![Kerio](https://img.shields.io/badge/Kerio-Connect_&_Control-2CA5E0?style=flat)
![Telegram](https://img.shields.io/badge/Telegram-Channel-2CA5E0?style=flat&logo=telegram&logoColor=white)

**English** · [Русский](./docs/ru/README.ru.md)
</div>

## 📑 Table of Contents

- [Community & Support](#-community--support)
- [Overview](#-overview)
- [Features](#-features)
- [Installation and Setup](#-installation-and-setup)
- [Configuring Kerio Products](#-configuring-kerio-products)
- [Advanced Settings](#-advanced-settings)
- [Contributing & Support](#-contributing--support)
- [License](#-license)

## 🌐 Community & Support

Join our Telegram channel for updates, announcements, and community support:

[![Telegram](https://img.shields.io/badge/Join-Telegram_Channel-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/kerio_updates_mirror)

## 📋 Overview

**Kerio Updates Mirror** is a solution for local caching and mirroring of updates for Kerio Control and Kerio Connect
products, which allows you to:

- Reduce internet traffic and speed up the update process
- Provide updates for isolated networks or systems with limited internet access
- Automatically download and update antivirus databases, IPS/IDS Snort databases, and other security components

## 📊 Features

### Kerio Control

- **Scheduled updates** - automatic daily updates at a configured time for:
    - Web Filter content filtering subsystem key
    - IPS/IDS databases
    - Snort rule templates
    - GeoIP database
- **Shield Matrix** - automatic updates of Shield Matrix signatures and blacklists
- **Antivirus databases** - downloaded automatically when Kerio Control accesses the mirror, with a choice of
  update modes:
    - *Direct Mode* - antivirus updates go straight to the vendor, bypassing the mirror
    - *Proxy Mode* - updates are relayed through the mirror without local caching
    - *Mirror Mode* - updates are cached by the mirror for fast, bandwidth-saving repeat access

### Kerio Connect

- **Antivirus databases** - downloaded automatically when Kerio Connect accesses the mirror, using the same
  Direct / Proxy / Mirror modes as above
- **Antispam databases** - downloaded automatically when Kerio Connect accesses the mirror:
    - *Proxy Mode* - antispam updates are relayed through the mirror without local caching
    - *Mirror Mode* - antispam updates are cached by the mirror
- **Antispam request proxying** - antispam traffic can be routed through an upstream proxy or VPN

### Security & Access Control

- Authentication for the web management interface
- Restrict access to the web interface by IP, with CIDR range support
- Restrict access to Kerio update endpoints by IP, with CIDR range support

### Networking

- **Outbound proxy support** - HTTP/HTTPS and SOCKS5 proxy support for all outbound requests made by the mirror

## 🚀 Installation and Setup

#### Prerequisites

- Docker and Docker Compose ([installation guide](./docs/en/docker.md))

#### Option 1: Running from pre-built Docker images (recommended)

Uses ready-made images, so nothing is compiled locally - the fastest way to get started.

1. [Download Docker images](https://t.me/my_store_files_bot?start=kerio-updates-mirror)
2. Load images from archives:
   ```bash
    sudo docker load -i kum_nginx_vX.X.X.tar
    sudo docker load -i mirror_vX.X.X.tar
    sudo docker load -i kum_xray_vX.X.X.tar
    sudo docker load -i kum_tor_vX.X.X.tar
   ```
   > Replace `X.X.X` with the actual version numbers from the filenames of the archives you downloaded.
3. Download or clone the repository:
   ```bash
   git clone https://github.com/cnekTep/kerio-updates-mirror.git
   cd kerio-updates-mirror
   ```
4. Start the containers:
   ```bash
   sudo docker compose up -d
   ```

#### Option 2: Building from source code

Builds all images locally from the repository source instead of using pre-built ones.

1. Download or clone the repository:
   ```bash
   git clone https://github.com/cnekTep/kerio-updates-mirror.git
   cd kerio-updates-mirror
   ```
2. Build and start the containers:
   ```bash
   sudo docker compose up -d --build
   ```

#### Option 3: Importing a Ready-to-Use Virtual Machine

This option provides a fully configured out-of-the-box solution, ideal for quick deployment.

1. [Download the Virtual Machine](https://boosty.to/kerio_updates)
2. Import the image into your virtualization system (Hyper-V, VMWare - OVF Template)
3. Start the virtual machine

<details>
<summary>📝 Hyper-V Import Instructions</summary>

1. Open **Hyper-V Manager**
2. In the **Action** menu, select **New** → **Virtual Machine**
3. In the creation wizard:
    - Enter a name for the virtual machine (for example, "Kerio Updates Mirror")
    - If needed, change the VM file location
    - Click **Next**
4. **Important**: In the generation selection section, choose **Generation 1**
5. Specify the amount of RAM (512-1024 MB recommended)
6. Configure network connection (select an existing virtual switch)
7. At the virtual hard disk configuration step:
    - Select **Use an existing virtual hard disk**
    - Click **Browse** and specify the path to the downloaded `.vhdx` file
    - Click **Next**
8. Review the parameter summary and click **Finish**

</details>

<details>
<summary>📝 VMware Import Instructions</summary>

##### Step-by-step import instructions for VMware Workstation/Player

1. Launch VMware Workstation or VMware Player
2. Select **File** → **Open**
3. Find and select the `.ovf` file from the unpacked archive
4. In the import dialog:
    - Specify the virtual machine name (for example, "Kerio Updates Mirror")
    - If needed, change the virtual machine location
    - Click **Import**
5. Wait for the import process to complete

##### Step-by-step import instructions for VMware ESXi

1. Log in to the VMware ESXi or vSphere web interface
2. Navigate to the **Virtual Machines** section
3. Click **Create/Register Virtual Machine**
4. Select **Deploy a virtual machine from OVF or OVA file**
5. Specify the virtual machine name
6. Drag and drop the OVF and VMDK files to the upload area or use the file selection button
7. Select storage for the VM placement
8. Select a network for connection
9. Click **Next** and then **Finish**

</details>

<details>
<summary>📝 Virtual Machine Specifications and Setup</summary>

##### Technical Specifications

- **Operating System**: Debian 12 (minimal installation)
- **Pre-installed Software**: SSH, Midnight Commander, htop, ncdu, Docker, Docker Compose
- **Docker Containers**: Portainer, Kerio Updates Mirror

##### System Access

> ⚠️ **Security warning**: the virtual machine ships with default credentials for both SSH/root and Portainer.
> Change **both** passwords immediately after the first login - leaving them unchanged exposes the server to
> unauthorized access.

- **Default Credentials**:
    - Username: `root`
    - Password: `root`

##### Initial Setup

1. Connect to the virtual machine via SSH (port 22)
2. ⚠️ **Change the root password immediately**:
   ```bash
   passwd
   ```
3. Configure the correct timezone:
   ```bash
   dpkg-reconfigure tzdata
   ```
4. Check the current IP address (DHCP is used by default):
   ```bash
   ip a
   ```

##### Network Configuration

To change network parameters:

1. Edit network interfaces:
   ```bash
   nano /etc/network/interfaces
   # or
   mc # then navigate to /etc/network/interfaces
   ```
2. Configure DNS servers:
   ```bash
   nano /etc/resolv.conf
   # or
   mc # then navigate to /etc/resolv.conf
   ```

##### Management via Portainer

The virtual machine includes pre-installed Portainer for convenient Docker container management:

- **URL**: `https://VIRTUAL_MACHINE_IP:9443`
- **Credentials**:
    - Username: `admin`
    - Password: `admin`

> ⚠️ **Change the Portainer admin password immediately** after the first login - the default credentials are publicly
> known and must not be left active.

</details>

## ⚙️ Configuring Kerio Products

### Kerio Connect

To configure updates through the local mirror in Kerio Connect, you need to specify an HTTP proxy server in the
settings:

<details>
<summary>Kerio Connect Configuration (click to expand)</summary>

1. Go to **Configuration → Advanced Options → HTTP Proxy**
2. Specify:
    - **Address**: IP_address_of_server_with_Docker_containers
    - **Port**: 8118

</details>

### Kerio Control

To configure updates through the local mirror in Kerio Control, you need to add DNS records:

<details>
<summary>Kerio Control Configuration (click to expand)</summary>

1. Go to **Configuration → DNS → Local DNS Lookup**
2. Add the following records (where Update_server_IP is the IP address of the server with the mirror):

| IP Address       | Hostname                                 | Description              |
|------------------|------------------------------------------|--------------------------|
| Update_server_IP | kerio-updates-mirror.local               | Kerio Updates Mirror     |
| Update_server_IP | bda-update.kerio.com                     | Antispam                 |
| Update_server_IP | bdupdate.kerio.com                       | Antivirus                |
| Update_server_IP | download.kerio.com                       | IDS/IPS - Snort Template |
| Update_server_IP | ids-update.kerio.com                     | IDS/IPS/GeoIP            |
| Update_server_IP | prod-update.kerio.com                    | Distributive Update      |
| Update_server_IP | register.kerio.com                       | Registration Info        |
| Update_server_IP | shieldmatrix-updates.gfikeriocontrol.com | ShieldMatrix             |
| Update_server_IP | wf-activation.kerio.com                  | WebFilter                |

</details>

## 🔧 Advanced Settings

### TOR Bridge Configuration

TOR bridges are used to ensure access to updates even in case of access restrictions:

- TOR bridges configuration file: `_tor/bridges/user_bridges.config`
- The system automatically checks internet accessibility through TOR and updates bridges if necessary
- New bridges can be obtained from the [official website](https://bridges.torproject.org) or
  via [Telegram bot](https://t.me/GetBridgesBot)

### Monitoring and Management

- Access to the web management interface:
    - `http://SERVER_IP/web`

## 🤝 Contributing & Support

Found a bug, have a feature request, or just want to ask a question? Join our Telegram chat - it's the fastest way
to reach the community and the maintainer:

[![Telegram](https://img.shields.io/badge/Join-Telegram_Chat-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/+XdMe68pac_cxZGVi)

Pull requests and issues on GitHub are also welcome.

## 📄 License

This project is free and open-source. The code is publicly available in this repository - feel free to use, study,
modify, and distribute it as you see fit.