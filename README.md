# Heard-Back-Yet

English | [中文](./README_ZH.md)

## 🚀Getting Started

This guide assumes you are using a Windows device.

```bash
git clone https://github.com/Kaichao-Zheng/Heard-Back-Yet.git
```

### Create a Virtual Environment

```bash
# create environment
python -m venv .venv         # or other name you like

# activate environment
source .venv/bin/activate    # macOS/Linux
.\.venv\Scripts\activate     # Windows Powershell
```

### Install Dependencies

```bash
pip install -r requirements.txt
python -m pip freeze > requirements.txt
```

### Configure Environment Variables

Copy the file `.env.example` and rename the file to `.env` in the root directory.

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=heardbackyet
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password
```