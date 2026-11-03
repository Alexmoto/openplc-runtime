# TargetVisu v0.8.0 — фоновое изображение экрана

## Что изменено

В свойствах **экрана** (а не отдельного Graphic View) можно выбрать фон:
- оставить прежнюю заливку `Background` (цвет);
- загрузить PNG/JPEG как `Screen background image`;
- выбрать масштабирование `Contain` / `Cover` / `Stretch`;
- удалить изображение, вернувшись к цветному фону.

Изображение рисуется под всеми элементами и сеткой Editor; не перехватывает нажатия.
Цвет фона сохраняется под прозрачными пикселями PNG. При удалении картинки фон снова
отображается цветом. В изображении нет привязки к переменной PLC: оно статическое,
устанавливается отдельно для каждого экрана.

Editor преобразует JPEG в PNG, ограничивает размер до 1024×1024 пикселей и 1 МиБ
PNG. Общий лимит TargetVisu JSON остаётся 4 МиБ, поэтому фон должен быть достаточно
сжат, особенно если в проекте много экранов и изображений.

Формат JSON:

```json
{
  "id": "main",
  "name": "Main",
  "width": 800,
  "height": 480,
  "background": "#f3f5f7",
  "backgroundGraphic": {
    "data": "data:image/png;base64,...",
    "fit": "cover"
  },
  "grid": 10,
  "elements": []
}
```

Поле `backgroundGraphic` необязательно. Старые проекты без него работают как прежде.

## Обновление Runtime на Banana Pi

Из отдельной Git-копии репозитория с сохранёнными изменениями:

```bash
cd /root/openplc-runtime-github
git status --short
git fetch origin feature/screen-background-image
git switch feature/screen-background-image
git pull --ff-only origin feature/screen-background-image

python3 updates/targetvisu-screen-bg-v0.8.0/install_update.py --runtime /root/openplc-runtime --check
python3 updates/targetvisu-screen-bg-v0.8.0/install_update.py --runtime /root/openplc-runtime
```

Не переключайте Git-ветку при несохранённых изменениях; сначала сделайте резервную
копию или коммит. Если Git-копия уже совпадает с рабочим Runtime, переключение ветки
может изменить Python-файлы до вызова установщика.

Установщик обновляет только `tools/targetvisu/model.py`, `render.py`, `graphics.py`,
проверяет синтаксис Python и создаёт `targetvisu-screen-bg-backup-...`. Включены
предыдущие изменения `Number` и `Graphic View`. Он **не** трогает `viewer.py`,
PLC-проект, RETAIN, OPC DA и ядро C++.

При безопасном состоянии оборудования перезапустите только графическую сессию:

```bash
systemctl restart lightdm
```

Команда временно отключит локальный HMI. **Пересобирать `plc_main` не требуется**.

Чтобы откатить Python-изменения, восстановите три файла из напечатанного каталога
резервной копии и перезапустите LightDM. Не применяйте после v0.8.0 более старые
установщики TargetVisu v0.5.0/v0.6.0/v0.7.0.

## Обновление Editor на Windows

Из текущего исходного каталога Editor:

```powershell
cd "D:\Project_PLC\OpenPLC_Editor\editor-source"
git status --short
git fetch origin feature/screen-background-image
git switch feature/screen-background-image
git pull --ff-only origin feature/screen-background-image
npm run package
```

Если зависимости ещё не установлены, запустите `npm ci` перед сборкой.
Нужны Node.js 22 или 23 и npm 10+. Установочный файл появится в `dist`.
Новый Editor нужно установить на Windows; затем пересобрать/загрузить PLC-проект
с выбранным фоновым изображением.

## Проверка

После обновления выберите экран без выделенных элементов, задайте `Background`
и добавьте изображение через `Screen background image`. Проверьте три режима fit,
прозрачность, видимость кнопок и удаление изображения. На Banana Pi проверьте
правильность фона и работу нажатий.

Это тестовая функциональность в ветке `feature/screen-background-image`;
она основана на `feature/graphic-view-image-states`, в свою очередь зависящей
от `feature/number-dynamic-colors`. До слияния трёх PR в main обновляйте
Editor и Runtime согласованно.
