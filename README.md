========================================
            Telegram Task Planner Bot
========================================

Ссылка на бота: https://t.me/task_manager_Data_Managment_bot

Описание:
------------
Telegram Task Planner Bot – это многофункциональный бот для Telegram, 
позволяющий пользователям вести журнал записей и управлять списком задач. 
Бот позволяет добавлять, просматривать, обновлять и удалять записи и задачи, 
а также автоматически отправляет напоминания о приближении дедлайнов.

Функционал:
------------
1. Журнал записей:
   - Добавление новой записи о событиях дня.
   - Просмотр записей за указанную дату.

2. Управление задачами:
   - Добавление задачи с дедлайном.
     * При добавлении задачи пользователь вводит текст задачи.
     * Ввод года дедлайна вручную.
     * Выбор месяца из списка (январь, февраль, ... , декабрь).
     * Выбор числа из списка (с учётом количества дней в месяце и високосных годов).
     * Ввод времени дедлайна в формате HH:MM.
   - Просмотр задач за определённую дату.
   - Обновление задачи:
     * Выбор задачи для обновления из списка.
     * Возможность изменить текст задачи или оставить его без изменений.
     * Выбор нового статуса задачи с помощью кнопок «✅ выполнено» и «❌ не выполнено».
   - Удаление задач:
     * Удаление задач за указанную дату.
     * Удаление всех задач.
   - Удаление всех записей.

3. Напоминания о дедлайнах:
   - Автоматическая проверка дедлайнов с напоминаниями:
     * За 1 день до дедлайна.
     * За 1 час до дедлайна.
     * В момент наступления дедлайна.

Средства разработки:
---------------------
- Язык программирования: Python 3.x
- Основные библиотеки:
  * python-telegram-bot (асинхронный интерфейс)
  * pymongo для взаимодействия с MongoDB
  * nest_asyncio для работы с вложенными event loop
- База данных: MongoDB (используется для хранения записей и задач)
- Среда разработки: PyCharm (или любая другая IDE для Python)
- Скрипт можно запускать на любом сервере с поддержкой Python и доступом к MongoDB.

Использование:
---------------
- Отправьте команду /start для начала работы с ботом.
- Используйте интуитивно понятное меню и кнопки для навигации по функционалу.
- Следуйте инструкциям бота при добавлении, обновлении или просмотре записей и задач.
- Напоминания о дедлайнах отправляются автоматически, согласно установленным задачам.


