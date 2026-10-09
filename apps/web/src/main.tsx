import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { SoundLab } from "./SoundLab";
import { BoardStudio } from "./BoardStudio";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {window.location.pathname === "/sound-lab" ? <SoundLab />
      : window.location.pathname === "/board-studio" ? <BoardStudio /> : <App />}
  </React.StrictMode>,
);
