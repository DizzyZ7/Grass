import { useEffect, useState } from 'react';
import type { MouseEvent } from 'react';
import { makeSharePng } from '../lib/share-card';
import type { Player } from '../types';

interface Props { player: Player; location: string; color?: string; onClose: () => void; shareText: () => void; }
export default function ShareCard({ player, location, color, onClose, shareText }: Props) {
  const [preview, setPreview] = useState('');
  const [blob, setBlob] = useState<Blob | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false; let url = '';
    void makeSharePng(player, location, color).then(result => {
      if (cancelled) return;
      url = URL.createObjectURL(result); setBlob(result); setPreview(url);
    }).catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'PNG недоступен.'); });
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [player, location, color]);
  const shareImage = async () => {
    if (!blob) return;
    const file = new File([blob], 'TOUCH_GRASS_DizZy.png', { type: 'image/png' });
    const data: ShareData = { files: [file], text: 'Мне сказали трогать траву. Я написал для этого бота. 🌱' };
    if (navigator.canShare?.({files: [file]}) && navigator.share) {
      try { await navigator.share(data); return; }
      catch (err) { if (err instanceof DOMException && err.name === 'AbortError') return; }
    }
    // A Telegram WebView may not allow file-sharing; keep the image visible for long-press saving.
    setError('Сохраните карточку ниже и отправьте ее в Telegram.');
  };
  return <div className="modal-backdrop" onClick={onClose}>
    <section className="achievement-modal share-modal" role="dialog" aria-modal="true" aria-label="Поделиться карточкой"
      onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}>
      <div className="modal-head"><div><small>GRASS.OS / RECEIPT</small><h2>Чек на социализацию 🌱</h2></div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть">×</button></div>
      <p>Карточка рисуется на вашем устройстве — без загрузки личных данных на сторонний сервер.</p>
      {preview ? <img className="share-preview" src={preview} alt="PNG-карточка с вашим результатом"/> : <div className="share-placeholder">{error || 'Выращиваем PNG…'}</div>}
      {error && preview && <p className="panel-note" role="status">{error}</p>}
      <div className="share-actions">
        <button className="main-button" disabled={!blob} onClick={() => void shareImage()}>ОТПРАВИТЬ PNG ↗</button>
        {preview && <a href={preview} download="TOUCH_GRASS_DizZy.png" className="finish-button">Сохранить</a>}
        <button type="button" className="finish-button" onClick={shareText}>Поделиться ссылкой</button>
      </div>
      <p className="panel-note">Если Telegram не поддерживает системный шаринг файлов, удерживайте изображение и сохраните его.</p>
    </section>
  </div>;
}
