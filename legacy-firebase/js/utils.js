import { auth } from './firebase-config.js';
import { signOut, onAuthStateChanged } from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js';

export function showToast(message, type = 'info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  let iconClass = 'fa-info-circle';
  if (type === 'success') iconClass = 'fa-check-circle';
  if (type === 'error') iconClass = 'fa-exclamation-circle';
  if (type === 'warning') iconClass = 'fa-exclamation-triangle';

  toast.innerHTML = `
    <i class="fas ${iconClass} toast-icon"></i>
    <div class="toast-message">${escapeHtml(message)}</div>
    <button class="toast-close"><i class="fas fa-times"></i></button>
  `;

  container.appendChild(toast);

  const closeBtn = toast.querySelector('.toast-close');
  
  const removeToast = () => {
    toast.classList.add('hiding');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  };

  closeBtn.addEventListener('click', removeToast);
  setTimeout(removeToast, 3000);
}

export function showModal(title, contentHTML, actionsHTML = '') {
  let modal = document.getElementById('globalModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'globalModal';
    modal.className = 'modal';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title"></h3>
          <button class="modal-close" id="globalModalClose"><i class="fas fa-times"></i></button>
        </div>
        <div class="modal-body"></div>
        <div class="modal-footer" style="display: none;"></div>
      </div>
    `;
    document.body.appendChild(modal);
    
    document.getElementById('globalModalClose').addEventListener('click', closeModal);
  }

  modal.querySelector('.modal-title').textContent = title;
  modal.querySelector('.modal-body').innerHTML = contentHTML;
  
  const footer = modal.querySelector('.modal-footer');
  if (actionsHTML) {
    footer.innerHTML = actionsHTML;
    footer.style.display = 'flex';
  } else {
    footer.style.display = 'none';
  }

  modal.classList.add('active');
}

export function closeModal() {
  const modal = document.getElementById('globalModal');
  if (modal) {
    modal.classList.remove('active');
  }
}

export function formatCurrency(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR'
  }).format(amount);
}

export function formatDate(date) {
  if (!date) return '';
  const d = date.toDate ? date.toDate() : new Date(date);
  return d.toLocaleDateString();
}

export function formatDateTime(date) {
  if (!date) return '';
  const d = date.toDate ? date.toDate() : new Date(date);
  return d.toLocaleString();
}

export function formatDuration(minutes) {
  if (!minutes || minutes < 0) return '0m';
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function generateTicketNumber() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let result = 'TK-';
  for (let i = 0; i < 8; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export function generateId() {
  return Math.random().toString(36).substring(2, 15);
}

export function animateCounter(element, target, duration = 1000) {
  if (!element) return;
  const start = parseInt(element.innerText.replace(/[^0-9.-]+/g,"")) || 0;
  const increment = (target - start) / (duration / 16);
  let current = start;
  
  const timer = setInterval(() => {
    current += increment;
    if ((increment > 0 && current >= target) || (increment < 0 && current <= target)) {
      clearInterval(timer);
      element.innerText = target.toLocaleString();
    } else {
      element.innerText = Math.floor(current).toLocaleString();
    }
  }, 16);
}

export function setActiveNav(pageName) {
  document.querySelectorAll('.nav-link').forEach(link => {
    if (link.dataset.page === pageName) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });
}

export function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    sidebar.classList.toggle('open');
  }
}

export function handleLogout() {
  signOut(auth).then(() => {
    window.location.href = 'index.html';
  }).catch((error) => {
    showToast('Error logging out: ' + error.message, 'error');
  });
}

export function initPage(pageName) {
  setActiveNav(pageName);
  
  const menuToggle = document.getElementById('menuToggle');
  if (menuToggle) {
    menuToggle.addEventListener('click', toggleSidebar);
  }
  
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', handleLogout);
  }
  
  onAuthStateChanged(auth, (user) => {
    if (!user) {
      window.location.href = 'index.html';
    } else {
      const userNameEl = document.getElementById('userName');
      if (userNameEl) {
        userNameEl.textContent = user.displayName || user.email.split('@')[0];
      }
    }
  });
}

export function showLoading(container) {
  if (!container) return;
  container.innerHTML = `<div class="skeleton" style="width:100%; height: 100px;"></div>`;
}

export function hideLoading(container) {
  if (!container) return;
  container.innerHTML = '';
}

export function debounce(fn, delay) {
  let timeoutId;
  return function(...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn.apply(this, args), delay);
  };
}

export function confirmAction(message) {
  return new Promise((resolve) => {
    showModal(
      'Confirm Action',
      `<p>${escapeHtml(message)}</p>`,
      `
      <button class="btn btn-secondary" id="confirmCancelBtn">Cancel</button>
      <button class="btn btn-primary" id="confirmOkBtn">Confirm</button>
      `
    );
    
    document.getElementById('confirmCancelBtn').addEventListener('click', () => {
      closeModal();
      resolve(false);
    });
    
    document.getElementById('confirmOkBtn').addEventListener('click', () => {
      closeModal();
      resolve(true);
    });
  });
}

export function validateRequired(fields) {
  let isValid = true;
  for (const field of fields) {
    const el = document.getElementById(field);
    if (el && !el.value.trim()) {
      el.style.borderColor = 'var(--error-color)';
      isValid = false;
    } else if (el) {
      el.style.borderColor = 'var(--border-color)';
    }
  }
  return isValid;
}

export function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
