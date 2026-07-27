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
- **Antivirus databases** - downloaded automatically when Kerio Control accesses the mirror, with a choice of update
  modes:
    - *Direct Mode* - antivirus updates go straight to the vendor, bypassing the mirror
    - *Proxy Mode* - updates are relayed through the mirror without local caching
    - *Mirror Mode* - updates are cached by the mirror for fast, bandwidth-saving repeat access

### Kerio Connect

- **Antivirus databases** - downloaded automatically when Kerio Connect accesses the mirror, using the same Direct /
  Proxy / Mirror modes as above
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
    sudo docker load -i kum_mirror_vX.X.X.tar
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
<summary>📝 Import into Hyper-V</summary>

1. Open **Hyper-V Manager**.
2. Select **Action** → **New** → **Virtual Machine**.
3. In the New Virtual Machine Wizard:
    - enter a name for the virtual machine (for example, **Kerio Updates Mirror**);
    - change the VM location if needed;
    - click **Next**.
4. **Important:** select **Generation 1**.
5. Allocate **1024–2048 MB** of RAM.
6. Select an existing virtual switch.
7. On the virtual hard disk step:
    - select **Use an existing virtual hard disk**;
    - browse to the downloaded `.vhdx` file.
8. Click **Finish** and start the virtual machine.

</details>

<details>
<summary>📝 Import into VMware</summary>

##### VMware Workstation / Player

1. Start VMware Workstation or VMware Player.
2. Select **File** → **Open**.
3. Select the `.ovf` file from the extracted archive.
4. Specify:
    - the virtual machine name;
    - the VM location (if necessary).
5. Click **Import** and wait for the import to complete.

##### VMware ESXi

1. Open the ESXi or vSphere web interface.
2. Go to **Virtual Machines**.
3. Click **Create/Register VM**.
4. Select **Deploy a virtual machine from an OVF or OVA file**.
5. Enter the virtual machine name.
6. Upload the `.ovf` and `.vmdk` files.
7. Select the datastore and network.
8. Click **Finish** and wait for the deployment to complete.

</details>

<details>
<summary>📝 Import into Proxmox VE</summary>

1. Upload the backup file (`.vma.zst`) to the Proxmox server via SSH.
2. In the Proxmox web interface, open **Datacenter** → **Storage** → **local**.
3. Go to the **Backups** tab.
4. Select the uploaded backup and click **Restore**.
5. Adjust the following settings if necessary:
    - **VM ID**;
    - virtual machine name;
    - storage for the virtual disks.
6. Click **Restore** and wait for the restore process to complete.
7. Start the virtual machine.

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

Found a bug, have a feature request, or just want to ask a question? Join our Telegram chat - it's the fastest way to
reach the community and the maintainer:

[![Telegram](https://img.shields.io/badge/Join-Telegram_Chat-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/+XdMe68pac_cxZGVi)

Pull requests and issues on GitHub are also welcome.

## 📄 License

This project is free and open-source. The code is publicly available in this repository - feel free to use, study,
modify, and distribute it as you see fit.