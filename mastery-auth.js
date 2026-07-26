/*
  Shared Firebase Auth helper for all Mastery Path sites.
  All 37 sites share the same GitHub Pages origin (sigilipelli.github.io),
  so a sign-in on ANY site is automatically recognized on every other site --
  no separate "single sign-on" plumbing needed, just the same Firebase config
  and the same persistence layer (browser localStorage on that one origin).
*/
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  sendPasswordResetEmail,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

// These values are public by design -- Firebase web config is meant to ship in
// client-side code. Security comes from Firebase's server-side rules and the
// Authorized Domains list, not from keeping these secret.
const firebaseConfig = {
  apiKey: "AIzaSyBAG2Kgt78opGLs1_MQml2e1Ef8R8QfgGM",
  authDomain: "mastery-path-auth.firebaseapp.com",
  projectId: "mastery-path-auth",
  storageBucket: "mastery-path-auth.firebasestorage.app",
  messagingSenderId: "803474926285",
  appId: "1:803474926285:web:0ad412da8ef74dcf185784",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

window.masteryAuth = {
  auth,
  onAuthStateChanged: (cb) => onAuthStateChanged(auth, cb),
  login: (email, password) => signInWithEmailAndPassword(auth, email, password),
  register: (email, password) => createUserWithEmailAndPassword(auth, email, password),
  loginWithGoogle: () => signInWithPopup(auth, new GoogleAuthProvider()),
  logout: () => signOut(auth),
  resetPassword: (email) => sendPasswordResetEmail(auth, email),
};

// Fire a DOM event once we know the auth state, so page-level gate scripts
// (which load before this module resolves) can react without polling.
onAuthStateChanged(auth, (user) => {
  window.dispatchEvent(new CustomEvent("mastery-auth-ready", { detail: { user } }));
});
