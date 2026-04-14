import pymysql

# Forcer la version pour Django 4.2+ et 6.0
pymysql.version_info = (2, 2, 1, 'final', 0)
pymysql.install_as_MySQLdb()
