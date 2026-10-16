import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./app/App";
import { PetProvider } from "./context/PetContext";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <PetProvider>
        <App />
      </PetProvider>
    </BrowserRouter>
  </StrictMode>,
);
