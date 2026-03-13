'use strict';

// ============================================================
//  API URL — auto-detects local vs production
//  Replace the production URL after deploying to Railway
// ============================================================
const TG_API_URL = (() => {
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8080';
  }
  // TODO: replace with your Railway deployment URL after first deploy
  return 'https://breed-show-production.up.railway.app';
})();

// ============================================================
//  Telegram WebApp SDK reference
// ============================================================
const tg = window.Telegram && window.Telegram.WebApp
  ? window.Telegram.WebApp
  : {
      ready: () => {},
      expand: () => {},
      close: () => {},
      openLink: (url) => window.open(url, '_blank'),
      openTelegramLink: (url) => window.open(url, '_blank'),
      BackButton: { show: () => {}, hide: () => {}, onClick: () => {}, offClick: () => {} },
      initData: '',
      initDataUnsafe: {},
      colorScheme: 'light',
      themeParams: {},
      HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {} },
    };

// ============================================================
//  Application State
// ============================================================
const state = {
  mode: 'cats',
  page: 'catalog',
  prevPage: null,
  prevScrollTop: 0,
  pets: [],
  currentPetId: null,
  favorites: new Set(),   // Set of pet_id strings
  config: null,
  filters: {
    breed: '',
    gender: 'all',
    priceMin: 0,
    priceMax: 0,
    ageMin: 0,
    ageMax: 0,
    availableOnly: false,
  },
  tempFilters: null,
  loading: false,
  initData: '',
  subscriptions: [],
};

// ============================================================
//  Helpers
// ============================================================

function formatPrice(n) {
  if (!n && n !== 0) return '';
  return Number(n).toLocaleString('ru-RU') + '\u00a0₽';
}

function formatAge(months) {
  if (!months) return '< 1 мес.';
  const m = parseInt(months, 10);
  if (m < 12) {
    const mod10 = m % 10;
    const mod100 = m % 100;
    let suffix;
    if (mod100 >= 11 && mod100 <= 19) suffix = 'месяцев';
    else if (mod10 === 1) suffix = 'месяц';
    else if (mod10 >= 2 && mod10 <= 4) suffix = 'месяца';
    else suffix = 'месяцев';
    return `${m}\u00a0${suffix}`;
  }
  const years = Math.floor(m / 12);
  const remMonths = m % 12;
  const yMod10 = years % 10;
  const yMod100 = years % 100;
  let ySuffix;
  if (yMod100 >= 11 && yMod100 <= 19) ySuffix = 'лет';
  else if (yMod10 === 1) ySuffix = 'год';
  else if (yMod10 >= 2 && yMod10 <= 4) ySuffix = 'года';
  else ySuffix = 'лет';
  if (remMonths === 0) return `${years}\u00a0${ySuffix}`;
  const mMod10 = remMonths % 10;
  const mMod100 = remMonths % 100;
  let mSuffix;
  if (mMod100 >= 11 && mMod100 <= 19) mSuffix = 'месяцев';
  else if (mMod10 === 1) mSuffix = 'месяц';
  else if (mMod10 >= 2 && mMod10 <= 4) mSuffix = 'месяца';
  else mSuffix = 'месяцев';
  return `${years}\u00a0${ySuffix} ${remMonths}\u00a0${mSuffix}`;
}

function genderLabel(gender, mode) {
  if (mode === 'dogs') {
    return gender === 'male' ? '🐶 Кобель' : '🐩 Сука';
  }
  return gender === 'male' ? '🐱 Кот' : '🐈 Кошка';
}

function genderIcon(gender) {
  return gender === 'male' ? '♂' : '♀';
}

let toastTimer = null;
function showToast(msg, type = 'info') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast toast--${type} toast--visible`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove('toast--visible');
  }, 2800);
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function hasActiveFilters() {
  const f = state.filters;
  return (
    f.breed !== '' ||
    f.gender !== 'all' ||
    f.priceMin > 0 ||
    f.priceMax > 0 ||
    f.ageMin > 0 ||
    f.ageMax > 0 ||
    f.availableOnly
  );
}

function getFilteredPets() {
  const f = state.filters;
  return state.pets.filter((p) => {
    if (f.breed && !p.breed.toLowerCase().includes(f.breed.toLowerCase())) return false;
    if (f.gender !== 'all' && p.gender !== f.gender) return false;
    if (f.priceMin > 0 && p.price < f.priceMin) return false;
    if (f.priceMax > 0 && p.price > f.priceMax) return false;
    if (f.ageMin > 0 && p.age_months < f.ageMin) return false;
    if (f.ageMax > 0 && p.age_months > f.ageMax) return false;
    if (f.availableOnly && !p.available) return false;
    return true;
  });
}

// ============================================================
//  localStorage favorites
// ============================================================

const LS_KEY = 'bs_favorites';

function loadFavoritesLocal() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      state.favorites = new Set(arr.map(String));
    }
  } catch (_) {
    state.favorites = new Set();
  }
}

function saveFavoritesLocal() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify([...state.favorites]));
  } catch (_) {}
}

function toggleFavorite(petId) {
  const id = String(petId);
  if (state.favorites.has(id)) {
    state.favorites.delete(id);
    showToast('Удалено из сохранённых', 'info');
    try { tg.HapticFeedback.impactOccurred('light'); } catch (_) {}
  } else {
    state.favorites.add(id);
    showToast('Сохранено ⭐', 'success');
    try { tg.HapticFeedback.impactOccurred('medium'); } catch (_) {}
  }
  saveFavoritesLocal();
  updateFavButton(id);
  updateSavedBadge();
}

function updateFavButton(petId) {
  const isFav = state.favorites.has(String(petId));
  document.querySelectorAll(`[data-fav-id="${petId}"]`).forEach((btn) => {
    btn.classList.toggle('fav-btn--active', isFav);
    btn.setAttribute('aria-label', isFav ? 'Убрать из сохранённых' : 'Сохранить');
  });
}

function updateSavedBadge() {
  const badge = document.getElementById('tabSavedBadge');
  if (!badge) return;
  const count = state.favorites.size;
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : count;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

// ============================================================
//  API calls
// ============================================================

function trackEvent(event, data = {}) {
  const payload = {
    event,
    tg_user_id: tg.initDataUnsafe?.user?.id ? String(tg.initDataUnsafe.user.id) : null,
    ...data,
  };
  fetch(TG_API_URL + '/analytics/event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => {});
}

// ============================================================
//  Subscriptions
// ============================================================

function getTgUserId() {
  return tg.initDataUnsafe?.user?.id ? String(tg.initDataUnsafe.user.id) : null;
}

async function loadSubscriptions() {
  if (!state.initData && !getTgUserId()) return;
  try {
    state.subscriptions = await apiFetch('/tg/subscriptions');
  } catch (_) {
    state.subscriptions = [];
  }
}

async function createSubscription(mode, breed, label) {
  const data = await apiFetch('/tg/subscriptions', {
    method: 'POST',
    body: JSON.stringify({ mode, breed: breed || null, label }),
  });
  await loadSubscriptions();
  return data;
}

async function deleteSubscription(id) {
  await apiFetch(`/tg/subscriptions/${id}`, { method: 'DELETE' });
  state.subscriptions = state.subscriptions.filter((s) => s.id !== id);
}

function getSubscriptionForBreed(breed, mode) {
  return state.subscriptions.find(
    (s) => s.mode === mode && (s.breed || '').toLowerCase() === (breed || '').toLowerCase()
  ) || null;
}

function getSubscriptionForMode(mode) {
  return state.subscriptions.find((s) => s.mode === mode && !s.breed) || null;
}

async function apiFetch(path, options = {}) {
  const url = TG_API_URL + path;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.initData) {
    headers['X-TG-InitData'] = state.initData;
  }
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

async function loadConfig() {
  try {
    const cfg = await apiFetch('/tg/config');
    state.config = cfg;
  } catch (err) {
    console.warn('Could not load config:', err);
    // Use defaults
    state.config = {
      bots: {
        kittens_bot_url: 'https://t.me/kittens_buy_bot',
        puppies_bot_url: 'https://t.me/puppies_buy_bot',
      },
      links: {
        add_for_sale_url_template:
          'https://breed.show/add?utm_source=telegram&utm_medium=miniapp&utm_campaign={mode}',
      },
    };
  }
}

async function loadPets() {
  const params = new URLSearchParams({ mode: state.mode });
  const f = state.filters;
  if (f.breed) params.set('breed', f.breed);
  if (f.gender !== 'all') params.set('gender', f.gender);
  if (f.priceMin > 0) params.set('min_price', f.priceMin);
  if (f.priceMax > 0) params.set('max_price', f.priceMax);
  if (f.ageMin > 0) params.set('min_age', f.ageMin);
  if (f.ageMax > 0) params.set('max_age', f.ageMax);
  if (f.availableOnly) params.set('available_only', '1');

  const data = await apiFetch(`/pets?${params.toString()}`);
  state.pets = Array.isArray(data) ? data : [];
}

async function loadPetById(petId) {
  return apiFetch(`/pets/${petId}`);
}

// ============================================================
//  Bot deeplink helpers
// ============================================================

function getBotUrl(mode) {
  if (!state.config) return null;
  return mode === 'cats'
    ? state.config.bots.kittens_bot_url
    : state.config.bots.puppies_bot_url;
}

function getPetDeeplink(petId, mode) {
  const botUrl = getBotUrl(mode || state.mode);
  if (!botUrl) return null;
  return `${botUrl}?start=pet_${petId}`;
}

function sharePet(pet) {
  const deeplink = getPetDeeplink(pet.id, pet.mode || state.mode);
  if (!deeplink) {
    showToast('Не удалось получить ссылку', 'error');
    return;
  }
  const text = `${pet.name} — ${pet.breed}, ${formatAge(pet.age_months)}, ${formatPrice(pet.price)}`;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(deeplink)}&text=${encodeURIComponent(text)}`;
  try {
    tg.openTelegramLink(shareUrl);
  } catch (_) {
    window.open(shareUrl, '_blank');
  }
}

// ============================================================
//  Navigation
// ============================================================

function navigate(page, data = {}) {
  const prevPage = state.page;
  state.prevPage = prevPage;
  state.page = page;

  // Hide all pages
  document.querySelectorAll('.page').forEach((el) => el.classList.add('page--hidden'));

  const target = document.getElementById(`page${capitalize(page)}`);
  if (target) target.classList.remove('page--hidden');

  // Header
  updateHeader(page);
  // Tab bar
  updateTabBar(page);

  if (page === 'detail' && data.petId) {
    state.currentPetId = data.petId;
    renderDetail(data.petId);
  } else if (page === 'catalog') {
    renderCatalog();
  } else if (page === 'saved') {
    renderSaved();
  } else if (page === 'filters') {
    renderFilters();
  } else if (page === 'howto') {
    renderHowto();
  } else if (page === 'add') {
    renderAdd();
  }

  // Scroll to top on page change
  const container = document.getElementById('pageContainer');
  if (container) container.scrollTop = 0;
}

function goBack() {
  const prev = state.prevPage || 'catalog';
  navigate(prev);
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function updateHeader(page) {
  const backBtn = document.getElementById('headerBack');
  const titleEl = document.getElementById('headerTitle');
  const filterBtn = document.getElementById('headerFilterBtn');
  const filterBadge = document.getElementById('filterBadge');

  const titles = {
    catalog: state.mode === 'cats' ? '🐱 Котята' : '🐶 Щенки',
    filters: 'Фильтры',
    detail: '',
    saved: 'Сохранённые',
    howto: 'Как пользоваться',
    add: 'Подать объявление',
  };

  if (titleEl) titleEl.textContent = titles[page] || 'Breed Show';

  const showBack = page === 'detail' || page === 'filters' || page === 'add';
  if (backBtn) backBtn.hidden = !showBack;

  const showFilter = page === 'catalog';
  if (filterBtn) filterBtn.hidden = !showFilter;
  if (filterBadge) filterBadge.hidden = !hasActiveFilters();

  // Telegram native back button
  if (showBack) {
    tg.BackButton.show();
  } else {
    tg.BackButton.hide();
  }
}

function updateTabBar(page) {
  document.querySelectorAll('.tab-item').forEach((btn) => {
    btn.classList.toggle('tab-item--active', btn.dataset.tab === page);
  });
  // Hide tab bar on filters and add pages
  const tabBar = document.getElementById('tabBar');
  if (tabBar) tabBar.hidden = page === 'filters' || page === 'add';
}

// ============================================================
//  Render: Pet card (for catalog and saved grids)
// ============================================================

function renderPetCard(pet, opts = {}) {
  const isFav = state.favorites.has(String(pet.id));
  const { showCategoryBadge = false } = opts;

  const categoryEmoji = pet.mode === 'dogs' ? '🐶' : '🐱';
  const catBadge = showCategoryBadge
    ? `<span class="saved-category-badge">${categoryEmoji}</span>`
    : '';

  const promoBadge = pet.is_promoted
    ? `<span class="badge badge-promo">🔥 ТОП</span>`
    : '';
  const kennelBadge = pet.has_kennel_landing
    ? `<span class="badge badge-kennel">⭐ Питомник</span>`
    : '';
  const badgesHtml =
    promoBadge || kennelBadge
      ? `<div class="pet-badges">${promoBadge}${kennelBadge}</div>`
      : '';

  const unavailableOverlay = !pet.available
    ? `<div class="pet-card__unavailable">Недоступно</div>`
    : '';

  return `
    <article class="pet-card${!pet.available ? ' pet-card--unavailable' : ''}" data-pet-id="${escHtml(pet.id)}">
      <div class="pet-card__img-wrap">
        <img
          class="pet-card__img"
          src="${escHtml(pet.image)}"
          alt="${escHtml(pet.name)}"
          loading="lazy"
          onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%22300%22><rect fill=%22%23e8eef5%22 width=%22400%22 height=%22300%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 font-size=%2248%22>${pet.mode === 'dogs' ? '🐶' : '🐱'}</text></svg>'"
        >
        ${badgesHtml}
        ${catBadge}
        ${unavailableOverlay}
        <button
          class="fav-btn${isFav ? ' fav-btn--active' : ''}"
          data-fav-id="${escHtml(pet.id)}"
          aria-label="${isFav ? 'Убрать из сохранённых' : 'Сохранить'}"
          title="${isFav ? 'Убрать из сохранённых' : 'Сохранить'}"
        >
          ${isFav ? '⭐' : '☆'}
        </button>
      </div>
      <div class="pet-card__body">
        <div class="pet-card__top">
          <span class="pet-card__name">${escHtml(pet.name)}</span>
          <span class="pet-card__gender${pet.gender === 'female' ? ' pet-card__gender--female' : ''}">${genderIcon(pet.gender)}</span>
        </div>
        <div class="pet-card__breed">${escHtml(pet.breed)}</div>
        <div class="pet-card__meta">
          <span class="pet-card__age">${formatAge(pet.age_months)}</span>
          ${pet.color ? `<span class="pet-card__color">${escHtml(pet.color)}</span>` : ''}
        </div>
        <div class="pet-card__price">${formatPrice(pet.price)}</div>
      </div>
    </article>
  `;
}

function renderSkeletonCards(count = 3) {
  return Array.from({ length: count }, () => `
    <div class="pet-card pet-card--skeleton">
      <div class="skeleton skeleton--img"></div>
      <div class="pet-card__body">
        <div class="skeleton skeleton--text skeleton--text-lg"></div>
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text skeleton--text-sm"></div>
        <div class="skeleton skeleton--text skeleton--text-price"></div>
      </div>
    </div>
  `).join('');
}

// ============================================================
//  Render: Catalog
// ============================================================

function renderCatalog() {
  const grid = document.getElementById('petGrid');
  if (!grid) return;

  updateHeader('catalog');

  if (state.loading) {
    grid.innerHTML = renderSkeletonCards(3);
    return;
  }

  const filtered = getFilteredPets();

  if (filtered.length === 0) {
    const isEmpty = state.pets.length === 0;
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">${state.mode === 'cats' ? '🐱' : '🐶'}</div>
        <div class="empty-state__title">${isEmpty ? 'Питомцы не найдены' : 'Ничего не найдено'}</div>
        <div class="empty-state__text">
          ${isEmpty
            ? 'Попробуйте позже — скоро появятся новые питомцы.'
            : 'Попробуйте изменить фильтры.'}
        </div>
        ${!isEmpty ? `<button class="btn btn--primary mt-2" id="emptyResetFilters">Сбросить фильтры</button>` : ''}
      </div>
    `;
    const resetBtn = document.getElementById('emptyResetFilters');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        resetFilters();
        navigate('catalog');
      });
    }
    return;
  }

  // Subscribe button for active filters
  const subscribeBar = document.getElementById('catalogSubscribeBar');
  if (subscribeBar) {
    if (getTgUserId() && (state.filters.breed || state.filters.gender !== 'all' || state.filters.priceMin || state.filters.priceMax)) {
      const modeSub = getSubscriptionForMode(state.mode);
      const breedSub = state.filters.breed ? getSubscriptionForBreed(state.filters.breed, state.mode) : null;
      const activeSub = breedSub || modeSub;
      subscribeBar.hidden = false;
      if (activeSub) {
        subscribeBar.innerHTML = `<button class="subscribe-btn subscribe-btn--active subscribe-btn--bar" id="catalogSubBtn">🔔 Вы следите за этим фильтром</button>`;
        document.getElementById('catalogSubBtn').addEventListener('click', async () => {
          await deleteSubscription(activeSub.id);
          showToast('Подписка отменена', 'info');
          renderCatalog();
        });
      } else {
        subscribeBar.innerHTML = `<button class="subscribe-btn subscribe-btn--bar" id="catalogSubBtn">🔔 Следить за новыми объявлениями</button>`;
        document.getElementById('catalogSubBtn').addEventListener('click', async () => {
          await createSubscription(state.mode, state.filters.breed || null, '');
          showToast('Подписка создана 🔔', 'success');
          try { tg.HapticFeedback.notificationOccurred('success'); } catch (_) {}
          renderCatalog();
        });
      }
    } else {
      subscribeBar.hidden = true;
    }
  }

  grid.innerHTML = filtered.map((p) => renderPetCard(p)).join('');

  // Bind card click events
  grid.querySelectorAll('.pet-card').forEach((card) => {
    const petId = card.dataset.petId;
    card.addEventListener('click', (e) => {
      if (e.target.closest('.fav-btn')) return;
      navigate('detail', { petId });
    });
  });

  // Bind fav buttons
  grid.querySelectorAll('.fav-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFavorite(btn.dataset.favId);
      btn.textContent = state.favorites.has(btn.dataset.favId) ? '⭐' : '☆';
    });
  });
}

// ============================================================
//  Render: Detail
// ============================================================

async function renderDetail(petId) {
  const container = document.getElementById('detailContent');
  if (!container) return;

  // Show loading state
  container.innerHTML = `
    <div class="detail-loading">
      <div class="skeleton skeleton--detail-img"></div>
      <div class="detail-loading__body">
        <div class="skeleton skeleton--text skeleton--text-lg"></div>
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text"></div>
        <div class="skeleton skeleton--text skeleton--text-sm"></div>
      </div>
    </div>
  `;

  let pet;
  try {
    // Check if already in state.pets
    pet = state.pets.find((p) => String(p.id) === String(petId));
    if (!pet) {
      pet = await loadPetById(petId);
    }
  } catch (err) {
    if (err.message && err.message.includes('404')) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">🔍</div>
          <div class="empty-state__title">Питомец не найден</div>
          <div class="empty-state__text">Возможно, объявление было снято.</div>
          <button class="btn btn--primary mt-2" id="detailBackBtn">Вернуться в каталог</button>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">⚠️</div>
          <div class="empty-state__title">Ошибка загрузки</div>
          <div class="empty-state__text">${escHtml(err.message)}</div>
          <button class="btn btn--primary mt-2" id="detailRetryBtn">Повторить</button>
        </div>
      `;
      document.getElementById('detailRetryBtn')?.addEventListener('click', () => renderDetail(petId));
    }
    document.getElementById('detailBackBtn')?.addEventListener('click', () => navigate('catalog'));
    return;
  }

  // If pet mode differs from state.mode — update mode
  if (pet.mode && pet.mode !== state.mode) {
    state.mode = pet.mode;
    updateHeader('detail');
  }

  // Update page title
  const titleEl = document.getElementById('headerTitle');
  if (titleEl) titleEl.textContent = pet.name;

  const isFav = state.favorites.has(String(pet.id));

  if (pet.has_kennel_landing && pet.kennel_id) {
    trackEvent('kennel_view', { pet_id: String(pet.id), kennel_id: String(pet.kennel_id) });
  }

  const kennelBlock = pet.has_kennel_landing && pet.kennel_name
    ? `
      <div class="kennel-block">
        <span class="kennel-block__icon">🏠</span>
        <div class="kennel-block__info">
          <div class="kennel-block__label">Питомник</div>
          <div class="kennel-block__name">${escHtml(pet.kennel_name)}</div>
        </div>
        <button class="kennel-block__link" data-kennel-id="${escHtml(pet.kennel_id)}">
          Посмотреть →
        </button>
      </div>
    `
    : '';

  const tagsHtml = [
    `<span class="detail-tag">${formatAge(pet.age_months)}</span>`,
    `<span class="detail-tag">${genderLabel(pet.gender, pet.mode || state.mode)}</span>`,
    pet.color ? `<span class="detail-tag">${escHtml(pet.color)}</span>` : '',
    !pet.available ? `<span class="detail-tag detail-tag--unavail">Недоступно</span>` : '',
  ].filter(Boolean).join('');

  const promoBadge = pet.is_promoted ? `<span class="badge badge-promo">🔥 ТОП</span>` : '';
  const kennelBadge = pet.has_kennel_landing ? `<span class="badge badge-kennel">⭐ Питомник</span>` : '';

  container.innerHTML = `
    <div class="detail-card">
      <div class="detail-img-wrap">
        <img
          class="detail-img"
          src="${escHtml(pet.image)}"
          alt="${escHtml(pet.name)}"
          onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22400%22><rect fill=%22%23e8eef5%22 width=%22600%22 height=%22400%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 font-size=%2272%22>${pet.mode === 'dogs' ? '🐶' : '🐱'}</text></svg>'"
        >
        ${(promoBadge || kennelBadge) ? `<div class="pet-badges pet-badges--detail">${promoBadge}${kennelBadge}</div>` : ''}
      </div>

      <div class="detail-body">
        <div class="detail-header-row">
          <h1 class="detail-name">${escHtml(pet.name)}</h1>
          <span class="detail-price">${formatPrice(pet.price)}</span>
        </div>
        <div class="detail-breed">${escHtml(pet.breed)}</div>
        <div class="detail-tags">${tagsHtml}</div>

        ${pet.description ? `<p class="detail-desc">${escHtml(pet.description)}</p>` : ''}

        ${kennelBlock}

        <div class="detail-actions" id="detailActions">
          ${pet.telegram_url ? `
            <button class="contact-btn contact-btn--tg" id="btnContactTg">
              <span class="contact-btn__icon">💬</span>
              <span>Написать в Telegram</span>
            </button>
          ` : ''}
          ${pet.phone ? `
            <a class="contact-btn contact-btn--phone" href="tel:${escHtml(pet.phone)}">
              <span class="contact-btn__icon">📞</span>
              <span>${escHtml(pet.phone)}</span>
            </a>
          ` : ''}
          ${pet.email ? `
            <a class="contact-btn contact-btn--email" href="mailto:${escHtml(pet.email)}">
              <span class="contact-btn__icon">✉️</span>
              <span>${escHtml(pet.email)}</span>
            </a>
          ` : ''}
        </div>

        ${getTgUserId() ? `
        <div class="subscribe-block" id="subscribeBlock">
          <!-- filled after render -->
        </div>
        ` : ''}

        <div class="action-panel">
          <button class="action-panel__btn action-panel__btn--fav${isFav ? ' fav-btn--active' : ''}" id="detailFavBtn" data-fav-id="${escHtml(pet.id)}">
            ${isFav ? '⭐' : '☆'} ${isFav ? 'Сохранено' : 'Сохранить'}
          </button>
          <button class="action-panel__btn action-panel__btn--share" id="detailShareBtn">
            📤 Поделиться
          </button>
        </div>
      </div>
    </div>
  `;

  // Bind Telegram contact button
  const tgBtn = document.getElementById('btnContactTg');
  if (tgBtn && pet.telegram_url) {
    tgBtn.addEventListener('click', () => {
      try {
        tg.openTelegramLink(pet.telegram_url);
      } catch (_) {
        tg.openLink(pet.telegram_url);
      }
    });
  }

  // Bind fav button
  const favBtn = document.getElementById('detailFavBtn');
  if (favBtn) {
    favBtn.addEventListener('click', () => {
      toggleFavorite(pet.id);
      const nowFav = state.favorites.has(String(pet.id));
      favBtn.innerHTML = `${nowFav ? '⭐' : '☆'} ${nowFav ? 'Сохранено' : 'Сохранить'}`;
      favBtn.classList.toggle('fav-btn--active', nowFav);
    });
  }

  // Bind share button
  const shareBtn = document.getElementById('detailShareBtn');
  if (shareBtn) {
    shareBtn.addEventListener('click', () => sharePet(pet));
  }

  // Bind kennel link
  const kennelLinkBtn = container.querySelector('.kennel-block__link');
  if (kennelLinkBtn && pet.kennel_id) {
    kennelLinkBtn.addEventListener('click', () => {
      trackEvent('kennel_from_pet_click', { pet_id: String(pet.id), kennel_id: String(pet.kennel_id) });
      const url = `https://breed.show/kennel/${encodeURIComponent(pet.kennel_id)}`;
      tg.openLink(url);
    });
  }

  // Subscribe button
  const subscribeBlock = document.getElementById('subscribeBlock');
  if (subscribeBlock && pet.breed) {
    renderSubscribeButton(subscribeBlock, pet.mode || state.mode, pet.breed);
  }
}

function renderSubscribeButton(container, mode, breed) {
  const existing = getSubscriptionForBreed(breed, mode);
  if (existing) {
    container.innerHTML = `
      <button class="subscribe-btn subscribe-btn--active" id="subBtn">
        🔔 Вы следите за «${escHtml(breed)}»
      </button>
    `;
    document.getElementById('subBtn').addEventListener('click', async () => {
      try {
        await deleteSubscription(existing.id);
        renderSubscribeButton(container, mode, breed);
        showToast('Подписка отменена', 'info');
      } catch (_) {
        showToast('Ошибка', 'error');
      }
    });
  } else {
    container.innerHTML = `
      <button class="subscribe-btn" id="subBtn">
        🔔 Следить за новыми «${escHtml(breed)}»
      </button>
    `;
    document.getElementById('subBtn').addEventListener('click', async () => {
      try {
        await createSubscription(mode, breed, `Новые ${breed}`);
        renderSubscribeButton(container, mode, breed);
        showToast('Подписка создана 🔔', 'success');
        try { tg.HapticFeedback.notificationOccurred('success'); } catch (_) {}
      } catch (_) {
        showToast('Ошибка подписки', 'error');
      }
    });
  }
}

// ============================================================
//  Render: Saved
// ============================================================

function renderSubscriptionsList() {
  const el = document.getElementById('savedSubscriptions');
  if (!el) return;
  if (!getTgUserId() || state.subscriptions.length === 0) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const rows = state.subscriptions.map((s) => `
    <div class="sub-item">
      <div class="sub-item__info">
        <div class="sub-item__label">${escHtml(s.label)}</div>
        <div class="sub-item__meta">${s.mode === 'cats' ? '🐱 Котята' : '🐶 Щенки'}${s.breed ? ' · ' + escHtml(s.breed) : ''}</div>
      </div>
      <button class="sub-item__del" data-sub-id="${s.id}" aria-label="Удалить подписку">✕</button>
    </div>
  `).join('');
  el.innerHTML = `
    <div class="sub-section">
      <div class="sub-section__title">🔔 Мои подписки</div>
      ${rows}
    </div>
  `;
  el.querySelectorAll('.sub-item__del').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await deleteSubscription(Number(btn.dataset.subId));
      renderSubscriptionsList();
      showToast('Подписка удалена', 'info');
    });
  });
}

async function renderSaved() {
  const grid = document.getElementById('savedGrid');
  if (!grid) return;

  renderSubscriptionsList();

  if (state.favorites.size === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">⭐</div>
        <div class="empty-state__title">Вы ещё ничего не сохранили</div>
        <div class="empty-state__text">Нажмите ☆ на карточке питомца, чтобы добавить в сохранённые.</div>
        <button class="btn btn--primary mt-2" id="savedGoCatalog">Перейти в каталог</button>
      </div>
    `;
    document.getElementById('savedGoCatalog')?.addEventListener('click', () => navigate('catalog'));
    return;
  }

  // Show skeleton while loading
  grid.innerHTML = renderSkeletonCards(Math.min(state.favorites.size, 3));

  // Fetch all saved pets in parallel
  const petIds = [...state.favorites];
  const results = await Promise.allSettled(
    petIds.map((id) => {
      const cached = [...state.pets, ...(window._savedCache || [])].find((p) => String(p.id) === String(id));
      if (cached) return Promise.resolve(cached);
      return loadPetById(id);
    })
  );

  const pets = [];
  const notFound = [];
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') {
      pets.push(r.value);
      window._savedCache = window._savedCache || [];
      if (!window._savedCache.find((p) => String(p.id) === String(r.value.id))) {
        window._savedCache.push(r.value);
      }
    } else {
      notFound.push(petIds[i]);
    }
  });

  if (pets.length === 0 && notFound.length === 0) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-state__icon">⭐</div><div class="empty-state__title">Пусто</div></div>`;
    return;
  }

  let html = pets.map((p) => renderPetCard(p, { showCategoryBadge: true })).join('');

  notFound.forEach((id) => {
    html += `
      <div class="pet-card pet-card--unavailable pet-card--notfound">
        <div class="pet-card__body">
          <div class="pet-card__name">Питомец #${escHtml(id)}</div>
          <div class="pet-card__breed">Объявление недоступно</div>
          <button class="btn btn--outline btn--small mt-1 remove-saved-btn" data-id="${escHtml(id)}">Удалить из сохранённых</button>
        </div>
      </div>
    `;
  });

  grid.innerHTML = html;

  // Bind card clicks
  grid.querySelectorAll('.pet-card').forEach((card) => {
    const petId = card.dataset.petId;
    if (!petId) return;
    card.addEventListener('click', (e) => {
      if (e.target.closest('.fav-btn') || e.target.closest('.remove-saved-btn')) return;
      navigate('detail', { petId });
    });
  });

  // Bind fav buttons
  grid.querySelectorAll('.fav-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFavorite(btn.dataset.favId);
      btn.textContent = state.favorites.has(btn.dataset.favId) ? '⭐' : '☆';
      setTimeout(() => renderSaved(), 300);
    });
  });

  // Bind remove not-found buttons
  grid.querySelectorAll('.remove-saved-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      state.favorites.delete(String(id));
      saveFavoritesLocal();
      updateSavedBadge();
      renderSaved();
    });
  });
}

// ============================================================
//  Render: Filters
// ============================================================

function renderFilters() {
  // Clone current filters to temp
  state.tempFilters = { ...state.filters };

  const f = state.tempFilters;

  // Breed
  const breedInput = document.getElementById('filterBreed');
  if (breedInput) breedInput.value = f.breed || '';

  // Price
  const priceMin = document.getElementById('filterPriceMin');
  const priceMax = document.getElementById('filterPriceMax');
  if (priceMin) priceMin.value = f.priceMin > 0 ? f.priceMin : '';
  if (priceMax) priceMax.value = f.priceMax > 0 ? f.priceMax : '';

  // Age
  const ageMin = document.getElementById('filterAgeMin');
  const ageMax = document.getElementById('filterAgeMax');
  if (ageMin) ageMin.value = f.ageMin > 0 ? f.ageMin : '';
  if (ageMax) ageMax.value = f.ageMax > 0 ? f.ageMax : '';

  // Available toggle
  const availToggle = document.getElementById('filterAvailable');
  if (availToggle) availToggle.checked = !!f.availableOnly;

  // Gender chips — vary by mode
  const chipsContainer = document.getElementById('genderChips');
  if (chipsContainer) {
    const isCats = state.mode === 'cats';
    const chips = [
      { value: 'all', label: 'Все' },
      { value: 'male', label: isCats ? 'Коты' : 'Кобели' },
      { value: 'female', label: isCats ? 'Кошки' : 'Суки' },
    ];
    chipsContainer.innerHTML = chips
      .map(
        (c) => `
          <button
            class="gender-chip${f.gender === c.value ? ' gender-chip--active' : ''}"
            data-gender="${c.value}"
          >${escHtml(c.label)}</button>
        `
      )
      .join('');

    chipsContainer.querySelectorAll('.gender-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        state.tempFilters.gender = chip.dataset.gender;
        chipsContainer.querySelectorAll('.gender-chip').forEach((c) => {
          c.classList.toggle('gender-chip--active', c.dataset.gender === state.tempFilters.gender);
        });
      });
    });
  }

  // Bind input changes to tempFilters
  if (breedInput) {
    breedInput.oninput = () => { state.tempFilters.breed = breedInput.value.trim(); };
  }
  if (priceMin) priceMin.oninput = () => { state.tempFilters.priceMin = parseInt(priceMin.value, 10) || 0; };
  if (priceMax) priceMax.oninput = () => { state.tempFilters.priceMax = parseInt(priceMax.value, 10) || 0; };
  if (ageMin) ageMin.oninput = () => { state.tempFilters.ageMin = parseInt(ageMin.value, 10) || 0; };
  if (ageMax) ageMax.oninput = () => { state.tempFilters.ageMax = parseInt(ageMax.value, 10) || 0; };
  if (availToggle) availToggle.onchange = () => { state.tempFilters.availableOnly = availToggle.checked; };

  // Subscribe button on filters page
  if (getTgUserId()) {
    renderFilterSubscribeButton();
    if (breedInput) breedInput.addEventListener('input', renderFilterSubscribeButton);
  }
}

function renderFilterSubscribeButton() {
  const bar = document.getElementById('filterSubscribeBar');
  if (!bar) return;
  const breed = (state.tempFilters?.breed || '').trim();
  const mode = state.mode;
  const existing = breed
    ? getSubscriptionForBreed(breed, mode)
    : getSubscriptionForMode(mode);

  bar.hidden = false;
  if (existing) {
    bar.innerHTML = `<button class="subscribe-btn subscribe-btn--active subscribe-btn--bar" id="filterSubBtn">🔔 Вы следите за этим фильтром</button>`;
    document.getElementById('filterSubBtn').addEventListener('click', async () => {
      await deleteSubscription(existing.id);
      renderFilterSubscribeButton();
      showToast('Подписка отменена', 'info');
    });
  } else {
    const label = breed
      ? `🔔 Следить за новыми «${breed}»`
      : `🔔 Следить за новыми объявлениями`;
    bar.innerHTML = `<button class="subscribe-btn subscribe-btn--bar" id="filterSubBtn">${escHtml(label)}</button>`;
    document.getElementById('filterSubBtn').addEventListener('click', async () => {
      await createSubscription(mode, breed || null, '');
      renderFilterSubscribeButton();
      showToast('Подписка создана 🔔', 'success');
      try { tg.HapticFeedback.notificationOccurred('success'); } catch (_) {}
    });
  }
}

function applyFilters() {
  if (state.tempFilters) {
    state.filters = { ...state.tempFilters };
    state.tempFilters = null;
  }
  navigate('catalog');
  loadAndRenderCatalog();
}

function resetFilters() {
  state.filters = {
    breed: '',
    gender: 'all',
    priceMin: 0,
    priceMax: 0,
    ageMin: 0,
    ageMax: 0,
    availableOnly: false,
  };
  state.tempFilters = null;
}

// ============================================================
//  Render: Howto
// ============================================================

// ============================================================
//  Render: Add listing form
// ============================================================

function renderAdd() {
  const container = document.getElementById('addFormBody');
  if (!container) return;

  container.innerHTML = `
    <div class="add-card">
      <div class="add-card__title">О питомце</div>
      <div class="add-field">
        <label>Порода <span class="req">*</span></label>
        <input id="afBreed" type="text" placeholder="Например: Британская короткошёрстная">
      </div>
      <div class="add-field">
        <label>Имя питомца</label>
        <input id="afName" type="text" placeholder="Например: Барсик">
      </div>
      <div class="add-row">
        <div class="add-field">
          <label>Возраст (мес.)</label>
          <input id="afAge" type="number" min="0" max="240" placeholder="3">
        </div>
        <div class="add-field">
          <label>Цвет</label>
          <input id="afColor" type="text" placeholder="голубой">
        </div>
      </div>
      <div class="add-field">
        <label>Пол</label>
        <div class="add-gender">
          <div class="add-gender-btn active" id="afGMale" onclick="afSetGender('male')">♂ Мальчик</div>
          <div class="add-gender-btn" id="afGFemale" onclick="afSetGender('female')">♀ Девочка</div>
        </div>
      </div>
      <div class="add-field">
        <label>Цена, ₽</label>
        <input id="afPrice" type="number" min="0" placeholder="35000">
      </div>
      <div class="add-field">
        <label>Описание <span class="req">*</span></label>
        <textarea id="afDesc" placeholder="Расскажите о питомце: документы, прививки, характер…"></textarea>
      </div>
    </div>

    <div class="add-card">
      <div class="add-card__title">Фото</div>
      <div class="add-field">
        <div class="add-photo-row">
          <input id="afPhoto" type="url" placeholder="https://… или загрузите файл">
          <label class="add-upload-btn">📷 <input type="file" accept="image/*" onchange="afUploadPhoto(this)"></label>
        </div>
        <div class="add-upload-status" id="afUploadStatus"></div>
        <img id="afPhotoPreview" class="add-photo-preview" alt="">
      </div>
    </div>

    <div class="add-card">
      <div class="add-card__title">Контакты</div>
      <div class="add-field">
        <label>Telegram <span class="req">*</span></label>
        <input id="afTelegram" type="text" placeholder="@username или https://t.me/…">
      </div>
      <div class="add-field">
        <label>Телефон</label>
        <input id="afPhone" type="tel" placeholder="+7 900 000-00-00">
      </div>
      <div class="add-field">
        <label>Питомник (если есть)</label>
        <input id="afKennel" type="text" placeholder="Название питомника">
      </div>
    </div>

    <div class="add-error" id="afError"></div>
    <button class="add-submit-btn" id="afSubmitBtn" onclick="afSubmit()">Отправить заявку</button>
  `;

  document.getElementById('afPhoto').addEventListener('input', function () {
    const img = document.getElementById('afPhotoPreview');
    img.src = this.value;
    img.style.display = this.value ? 'block' : 'none';
  });

  window._afGender = 'male';
}

window.afSetGender = function(g) {
  window._afGender = g;
  document.getElementById('afGMale').classList.toggle('active', g === 'male');
  document.getElementById('afGFemale').classList.toggle('active', g === 'female');
};

window.afUploadPhoto = async function(input) {
  if (!input.files || !input.files[0]) return;
  const status = document.getElementById('afUploadStatus');
  status.textContent = '⏳ Загружаю…';
  status.style.color = 'var(--text-muted)';
  try {
    const form = new FormData();
    form.append('file', input.files[0]);
    const headers = {};
    if (tg.initData) headers['X-TG-InitData'] = tg.initData;
    const resp = await fetch(TG_API_URL + '/api/upload-public', { method: 'POST', body: form, headers });
    const data = await resp.json();
    if (data && data.url) {
      document.getElementById('afPhoto').value = data.url;
      const img = document.getElementById('afPhotoPreview');
      img.src = data.url; img.style.display = 'block';
      status.textContent = '✅ Загружено'; status.style.color = 'var(--success)';
    } else {
      status.textContent = '❌ ' + (data.error || 'Ошибка'); status.style.color = 'var(--danger)';
    }
  } catch (e) {
    status.textContent = '❌ ' + e.message; status.style.color = 'var(--danger)';
  }
};

window.afSubmit = async function() {
  const breed = (document.getElementById('afBreed')?.value || '').trim();
  const desc = (document.getElementById('afDesc')?.value || '').trim();
  const telegram = (document.getElementById('afTelegram')?.value || '').trim();
  const errEl = document.getElementById('afError');

  errEl.style.display = 'none';
  if (!breed) { errEl.textContent = 'Пожалуйста, укажите породу'; errEl.style.display = 'block'; return; }
  if (!desc) { errEl.textContent = 'Пожалуйста, добавьте описание'; errEl.style.display = 'block'; return; }
  if (!telegram) { errEl.textContent = 'Пожалуйста, укажите Telegram для связи'; errEl.style.display = 'block'; return; }

  const btn = document.getElementById('afSubmitBtn');
  btn.disabled = true; btn.textContent = 'Отправляю…';

  const payload = {
    mode: state.mode,
    breed,
    name: (document.getElementById('afName')?.value || '').trim(),
    age_months: parseInt(document.getElementById('afAge')?.value) || 0,
    color: (document.getElementById('afColor')?.value || '').trim(),
    gender: window._afGender || 'male',
    price: parseInt(document.getElementById('afPrice')?.value) || 0,
    description: desc,
    photo_url: (document.getElementById('afPhoto')?.value || '').trim(),
    contact_telegram: telegram,
    contact_phone: (document.getElementById('afPhone')?.value || '').trim(),
    kennel_name: (document.getElementById('afKennel')?.value || '').trim(),
  };

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (tg.initData) headers['X-TG-InitData'] = tg.initData;
    const resp = await fetch(TG_API_URL + '/api/submit-listing', { method: 'POST', headers, body: JSON.stringify(payload) });
    const data = await resp.json();
    if (data && data.ok) {
      document.getElementById('addFormBody').innerHTML = `
        <div class="add-success">
          <div class="add-success__icon">✅</div>
          <div class="add-success__title">Заявка отправлена!</div>
          <div class="add-success__text">Мы проверим информацию и опубликуем объявление в течение нескольких часов. Спасибо!</div>
        </div>`;
      tg.HapticFeedback && tg.HapticFeedback.notificationOccurred('success');
    } else {
      errEl.textContent = data.error || 'Ошибка отправки. Попробуйте ещё раз.';
      errEl.style.display = 'block';
      btn.disabled = false; btn.textContent = 'Отправить заявку';
    }
  } catch (e) {
    errEl.textContent = 'Ошибка сети: ' + e.message;
    errEl.style.display = 'block';
    btn.disabled = false; btn.textContent = 'Отправить заявку';
  }
};

function renderHowto() {
  const addBtn = document.getElementById('btnAddForSale');
  if (addBtn) {
    addBtn.onclick = () => navigate('add');
  }
}

// ============================================================
//  Load and render catalog (with loading state)
// ============================================================

async function loadAndRenderCatalog() {
  state.loading = true;
  renderCatalog(); // shows skeletons

  try {
    await loadPets();
  } catch (err) {
    state.loading = false;
    const grid = document.getElementById('petGrid');
    if (grid) {
      grid.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">⚠️</div>
          <div class="empty-state__title">Ошибка загрузки</div>
          <div class="empty-state__text">${escHtml(err.message)}</div>
          <button class="btn btn--primary mt-2" id="retryLoadBtn">Повторить</button>
        </div>
      `;
      document.getElementById('retryLoadBtn')?.addEventListener('click', () => loadAndRenderCatalog());
    }
    return;
  }

  state.loading = false;
  renderCatalog();
}

// ============================================================
//  Tab bar & filter button event binding
// ============================================================

function bindNavEvents() {
  // Tab bar
  document.querySelectorAll('.tab-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      if (!tab) return;
      navigate(tab);
    });
  });

  // Header filter button
  const filterBtn = document.getElementById('headerFilterBtn');
  if (filterBtn) {
    filterBtn.addEventListener('click', () => navigate('filters'));
  }

  // Header back button
  const backBtn = document.getElementById('headerBack');
  if (backBtn) {
    backBtn.addEventListener('click', goBack);
  }

  // Telegram native back button
  tg.BackButton.onClick(goBack);

  // Filters apply / reset
  document.getElementById('btnApplyFilters')?.addEventListener('click', applyFilters);
  document.getElementById('btnResetFilters')?.addEventListener('click', () => {
    resetFilters();
    navigate('catalog');
    loadAndRenderCatalog();
  });
}

// ============================================================
//  Init
// ============================================================

async function init() {
  // Telegram ready
  tg.ready();
  tg.expand();

  // Get initData
  state.initData = tg.initData || '';

  // Read URL params
  const urlParams = new URLSearchParams(window.location.search);
  const modeParam = urlParams.get('mode');
  const petIdParam = urlParams.get('pet_id');

  // Set mode
  if (modeParam === 'cats' || modeParam === 'dogs') {
    state.mode = modeParam;
  } else {
    state.mode = 'cats'; // default
  }

  // Load favorites from localStorage
  loadFavoritesLocal();
  updateSavedBadge();

  // Bind navigation events
  bindNavEvents();

  // Load config and subscriptions (non-blocking)
  loadConfig().catch(() => {});
  loadSubscriptions().catch(() => {});

  if (petIdParam) {
    // Navigate to detail immediately, fetch pet (which may set mode)
    navigate('detail', { petId: petIdParam });
    // Also load the catalog in background for back-navigation
    loadPets().then(() => {}).catch(() => {});
  } else {
    // Load catalog
    await loadAndRenderCatalog();
    navigate('catalog');
  }
}

// Start
document.addEventListener('DOMContentLoaded', init);
