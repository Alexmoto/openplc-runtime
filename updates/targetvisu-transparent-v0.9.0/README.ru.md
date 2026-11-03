# TargetVisu v0.9.0 — прозрачные Button и Number

## Новые свойства

Для примитивов **Button** и **Number** в свойствах элемента доступны независимые флажки:

- `Transparent background` — не закрашивать прямоугольник;
- `Transparent border line` — не рисовать рамку.

При этом:
- Текст и числовое значение остаются видимыми.
- Цвета фона и рамки сохраняются в настройках и снова используются при снятии флажков.
- Уже реализованные переменные цвета `Number` продолжают работать при снятой прозрачности.
- Кнопка сохраняет **всю прямоугольную область нажатия** (а не только видимый текст/рамку).
- Действия `set`, `toggle`, `momentary`, `navigate` не изменяются; обработка нажатий и блокировки по PLC остаётся прежней.
- `Stroke width = 0` по-прежнему скрывает рамку. Новый флажок можно включить при ненулевой толщине, не теряя настройки.
- Другие примитивы не изменены.

Старые файлы TargetVisu без двух новых полей автоматически рассматриваются как `false`
(обычные непрозрачные фон и рамка). Картинка фона экрана и `Graphic View` остаются без изменений.

## Обновление Runtime на Banana Pi

При наличии отдельной копии Git (здесь `/root/openplc-runtime-github`):

```bash
cd /root/openplc-runtime-github
git status --short
git fetch origin feature/transparent-button-number
git switch feature/transparent-button-number
git pull --ff-only origin feature/transparent-button-number
python3 updates/targetvisu-transparent-v0.9.0/install_update.py --runtime /root/openplc-runtime --check
python3 updates/targetvisu-transparent-v0.9.0/install_update.py --runtime /root/openplc-runtime
```

Важно: если `git status --short` показывает изменения, сначала сохраните их,
не используйте `reset --hard`. Скрипт обновляет только `tools/targetvisu/model.py`
и `tools/targetvisu/render.py` и создаёт резервную копию
`targetvisu-transparent-backup-...` перед заменой. Не меняет C++,
`plc_main`, RETAIN, OPC DA, `viewer.py` и PLC-проект. После обновления в
безопасный момент перезапустите графический сеанс:

```bash
systemctl restart lightdm
```

Локальный HMI кратковременно прервётся. Пересобирать `plc_main` не нужно.
При необходимости откатите изменённые файлы из напечатанного каталога резервной копии.
Старые установщики v0.5–v0.8 запускать после v0.9 нельзя — они могут вернуть
старую реализацию графики.

## Editor на Windows

В исходном каталоге Editor:

```powershell
cd "D:\Project_PLC\OpenPLC_Editor\editor-source"
git status --short
git fetch origin feature/transparent-button-number
git switch feature/transparent-button-number
git pull --ff-only origin feature/transparent-button-number
npm run package
```

Если нет `node_modules`, предварительно `npm ci`. После сборки установите
созданный дистрибутив из каталога `dist`, затем пересоберите и загрузите
PLC-проект с новыми параметрами Button/Number.

## Проверка

1. Создайте Button поверх фоновой картинки экрана.
2. Включите оба флажка прозрачности.
3. Убедитесь, что виден только текст кнопки, но при касании любого места
   внутри её прямоугольной области действие выполняется.
4. Отключите прозрачность рамки — рамка вернётся с прежней толщиной и цветом.
5. Аналогично проверьте Number, включая его привязку цвета к PLC.
6. Для старого проекта без новых флажков убедитесь, что экран выглядит как прежде.

Версия основана на ветке `feature/screen-background-image`, поэтому
включает предыдущие изменения `Number`, `Graphic View` и фоновых картинок.
Ветки пока тестовые: после проверки GitHub Actions и на реальной Banana Pi
можно решать вопрос о слиянии с `main`.
