import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import AudioLibrary from "./AudioLibrary.jsx";
import "./styles.css";

const audioDemo = import.meta.env.VITE_AUDIO_DEMO_ONLY === "1";

createRoot(document.getElementById("root")).render(audioDemo
  ? <div className="layout"><main className="phone screen"><AudioLibrary /></main></div>
  : <App />);
