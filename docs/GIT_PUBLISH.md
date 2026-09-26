# GitHub: публикация этапа 3

Проект принадлежит DizZy. Локальный Git содержит коммиты этапов 1–3. Целевой GitHub: `https://github.com/DizzyZ7/Grass` (был пустым на момент подготовки; проверьте перед push). Эта среда не может выполнить `git push` напрямую, поэтому поставляется Git Bundle с полной историей.

```bash
# Запускается из папки со скачанным файлом .bundle
# Для пустого репозитория:
git clone -b main TOUCH_GRASS_exe_STAGE3.bundle Grass
cd Grass
git remote add origin https://github.com/DizzyZ7/Grass.git
git push -u origin main
```

Если репозиторий уже не пустой, сначала проверьте его историю через `git fetch` и согласуйте с локальными коммитами; не делайте `--force` вслепую. ZIP содержит те же исходники, что Bundle, но без полноценной истории Git. Не коммитьте `.env`, реальные токены или дампы БД.
