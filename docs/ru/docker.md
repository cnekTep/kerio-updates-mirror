# 🐳 Docker и Docker Compose - Руководство по установке

![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-A81D33?style=for-the-badge&logo=debian&logoColor=white)

Подробное руководство по установке Docker и Docker Compose в операционных системах Ubuntu и Debian.
> 📖 Это руководство представляет собой сокращенную версию официального руководства по установке Docker. Полную, всегда
> актуальную справочную информацию см. на
> сайте [docs.docker.com/engine/install](https://docs.docker.com/engine/install/).

## 📋 Содержание

- [Требования](#-требования)
- [Удаление старых версий](#-удаление-старых-версий)
- [Установка](#-установка)
- [Проверка установки](#-проверка-установки)

## 🔧 Требования

### Поддерживаемые операционные системы:

- **Ubuntu 26 (Resolute Raccoon)**
- **Ubuntu 24 (Noble Numbat)**
- **Ubuntu 22 (Jammy Jellyfish)**
- **Debian 13 (Trixie)**
- **Debian 12 (Bookworm)**
- **Debian 11 (Bullseye)**

### Системные требования:

- 64-битная архитектура (amd64)
- Привилегии администратора (sudo)
- Активное подключение к интернету

> ⚠️ **Все команды ниже показаны без `sudo`.** Сначала переключитесь на оболочку с повышенными правами и выполните все
> команды оттуда:
> - **Ubuntu**: `sudo su`
> - **Debian**: войдите в систему / переключитесь непосредственно на пользователя `root`

## 🗑️ Удаление старых версий

Перед установкой Docker Engine необходимо удалить все конфликтующие пакеты.

В вашем дистрибутиве Linux могут быть установлены неофициальные пакеты Docker, которые могут конфликтовать с
официальными пакетами, предоставляемыми Docker. Необходимо удалить эти пакеты перед установкой официальной версии Docker
Engine.

```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do apt remove $pkg; done
```

> ℹ️ Ничего страшного, если `apt` сообщит, что некоторые из этих пакетов "не установлены" - команда просто пропустит их.

## 🚀 Установка

### Шаг 1: Установка необходимых пакетов

Сначала установите дополнительные пакеты, необходимые для работы с репозиториями:

```bash
apt install curl ca-certificates -y
```

### Шаг 2: Импорт официального ключа GPG от Docker

Импортируйте официальный GPG-ключ Docker для вашей операционной системы:

#### 🟠 Для Ubuntu:

```bash
install -m 0755 -d /etc/apt/keyrings
```

```bash
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
```

```bash
chmod a+r /etc/apt/keyrings/docker.asc
```

#### 🔴 Для Debian:

```bash
install -m 0755 -d /etc/apt/keyrings
```

```bash
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
```

```bash
chmod a+r /etc/apt/keyrings/docker.asc
```

### Шаг 3: Добавление репозитория Docker

Добавьте официальный репозиторий Docker в список источников пакетов:

#### 🟠 Для Ubuntu:

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

#### 🔴 Для Debian:

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

### Шаг 4: Обновление индекса пакетов

Обновите список доступных пакетов:

```bash
apt update
```

### Шаг 5: Установка Docker пакетов

```bash
apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
```

## ✅ Проверка установки

После завершения установки проверьте корректность работы:

### Проверка версии Docker:

```bash
docker --version
```

### Проверка версии Docker Compose:

```bash
docker compose version
```

### Проверка статуса службы Docker:

```bash
systemctl status docker
```

### Тестовый запуск контейнера:

```bash
docker run hello-world
```

Если команда выводит приветственное сообщение, значит, Docker установлен и работает корректно.

## 📚 Дополнительная информация

Для получения информации о расширенных параметрах установки, других дистрибутивах Linux или устранения неполадок
обратитесь к официальной документации Docker: [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)