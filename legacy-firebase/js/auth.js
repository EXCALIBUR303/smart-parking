import { auth } from './firebase-config.js';
import { signInWithEmailAndPassword, createUserWithEmailAndPassword, sendPasswordResetEmail, onAuthStateChanged } from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js';
import { showToast } from './utils.js';

document.addEventListener('DOMContentLoaded', () => {
  // Check if already logged in
  onAuthStateChanged(auth, (user) => {
    if (user) {
      window.location.href = 'dashboard.html';
    }
  });

  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  
  const showRegisterBtn = document.getElementById('showRegister');
  const showLoginBtn = document.getElementById('showLogin');
  const forgotPasswordBtn = document.getElementById('forgotPassword');
  
  // Toggle forms
  if (showRegisterBtn) {
    showRegisterBtn.addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('loginSection').classList.remove('active');
      document.getElementById('registerSection').classList.add('active');
    });
  }
  
  if (showLoginBtn) {
    showLoginBtn.addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('registerSection').classList.remove('active');
      document.getElementById('loginSection').classList.add('active');
    });
  }

  if (forgotPasswordBtn) {
    forgotPasswordBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      const emailInput = document.getElementById('loginEmail');
      const email = emailInput.value.trim();

      if (!email) {
        emailInput.focus();
        showToast('Enter your email address to reset your password', 'error');
        return;
      }

      try {
        await sendPasswordResetEmail(auth, email);
        showToast('Password reset email sent. Check your inbox.', 'success');
      } catch (error) {
        showToast(error.message, 'error');
      }
    });
  }

  // Password toggle
  document.querySelectorAll('.password-toggle').forEach(btn => {
    btn.addEventListener('click', function() {
      const input = this.previousElementSibling;
      const icon = this.querySelector('i');
      if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
      } else {
        input.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
      }
    });
  });

  // Login handler
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('loginEmail').value;
      const password = document.getElementById('loginPassword').value;
      const btn = loginForm.querySelector('button[type="submit"]');
      
      try {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Logging in...';
        btn.disabled = true;
        await signInWithEmailAndPassword(auth, email, password);
        // onAuthStateChanged will handle redirect
      } catch (error) {
        showToast(error.message, 'error');
        btn.innerHTML = 'Sign In';
        btn.disabled = false;
      }
    });
  }

  // Register handler
  if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('regEmail').value;
      const password = document.getElementById('regPassword').value;
      const confirm = document.getElementById('regConfirmPassword').value;
      const btn = registerForm.querySelector('button[type="submit"]');

      if (password !== confirm) {
        showToast('Passwords do not match', 'error');
        return;
      }

      try {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registering...';
        btn.disabled = true;
        await createUserWithEmailAndPassword(auth, email, password);
        showToast('Registration successful!', 'success');
        // onAuthStateChanged will handle redirect
      } catch (error) {
        showToast(error.message, 'error');
        btn.innerHTML = 'Register';
        btn.disabled = false;
      }
    });
  }
});
