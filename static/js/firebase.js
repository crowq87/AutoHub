import { initializeApp } from "https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/12.0.0/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyDiyP6jDBLi2rh1y40D_hzwrmf4QunXVdY",
  authDomain: "autohub-3b.firebaseapp.com",
  projectId: "autohub-3b",
  storageBucket: "autohub-3b.firebasestorage.app",
  messagingSenderId: "12434264160",
  appId: "1:12434264160:web:df7f869ea01ad5ffd8f305"
};

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);