# 🐳 Docker и Docker Compose - Руководство по установке

![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-A81D33?style=for-the-badge&logo=debian&logoColor=white)

Подробное руководство по установке Docker и Docker Compose на операционные системы Ubuntu 24 и Debian 12.

## 📋 Содержание

- [Требования](#требования)
- [Установка](#установка)
- [Проверка установки](#проверка-установки)

## 🔧 Требования

### Поддерживаемые операционные системы:

- **Ubuntu 24 (Noble Numbat)**
- **Debian 12 (Bookworm)**

### Системные требования:

- 64-битная архитектура (amd64)
- Привилегии администратора (sudo)
- Активное подключение к интернету

## 🚀 Установка

### Шаг 1: Установка необходимых пакетов

Сначала установите дополнительные пакеты, необходимые для работы с репозиториями:

```bash
sudo apt install curl wget software-properties-common ca-certificates apt-transport-https -y
```

### Шаг 2: Импорт GPG-ключа Docker

Импортируйте официальный GPG-ключ Docker для вашей операционной системы:

#### 🟠 Для Ubuntu:

```bash
wget -O- https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor | sudo tee /etc/apt/keyrings/docker.gpg > /dev/null
```

#### 🔴 Для Debian:

```bash
wget -O- https://download.docker.com/linux/debian/gpg | gpg --dearmor | tee /etc/apt/keyrings/docker.gpg > /dev/null
```

### Шаг 3: Добавление репозитория Docker

Добавьте официальный репозиторий Docker в список источников пакетов:

#### 🟠 Для Ubuntu:

```bash
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

#### 🔴 Для Debian:

```bash
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### Шаг 4: Обновление индекса пакетов

Обновите список доступных пакетов:

```bash
sudo apt update
```

### Шаг 5: Установка Docker

Установите Docker Community Edition:

```bash
sudo apt install docker-ce -y
```

### Шаг 6: Установка Docker Compose

Установите Docker Compose:

```bash
sudo apt install docker-compose -y
```

## ✅ Проверка установки

После завершения установки проверьте корректность работы:

### Проверка версии Docker:

```bash
docker --version
```

### Проверка версии Docker Compose:

```bash
docker-compose --version
```

### Проверка статуса службы Docker:

```bash
sudo systemctl status docker
```

### Тестовый запуск контейнера:

```bash
sudo docker run hello-world
```