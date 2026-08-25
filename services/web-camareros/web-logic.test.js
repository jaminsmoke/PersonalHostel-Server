import { describe, expect, it } from "vitest";
import "./static/web-logic.js";

const logic = globalThis.PhWebLogic;
if (!logic) {
  throw new Error("PhWebLogic no se registró al cargar web-logic.js");
}
const { esc, clasificarFicha, clasificarInvitacion, mensajeLogin } = logic;

describe("esc", () => {
  it("escapa HTML en textos de ficha o login", () => {
    expect(esc('<img src=x onerror="alert(1)">')).toBe(
      "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
    );
    expect(esc("Ana & 'Pepe'")).toBe("Ana &amp; &#39;Pepe&#39;");
  });

  it("trata null y undefined como vacío", () => {
    expect(esc(null)).toBe("");
    expect(esc(undefined)).toBe("");
  });
});

describe("clasificarFicha", () => {
  it("marca QR inválido por código o 422", () => {
    expect(clasificarFicha(422, "identity.qr_invalido").titulo).toBe(
      "QR no válido",
    );
    expect(clasificarFicha(422, "").titulo).toBe("QR no válido");
  });

  it("marca credencial inactiva por código o 409", () => {
    expect(clasificarFicha(409, "identity.credencial_inactiva").titulo).toBe(
      "Credencial no activa",
    );
    expect(clasificarFicha(409, "").titulo).toBe("Credencial no activa");
  });

  it("cae a error genérico en el resto", () => {
    expect(clasificarFicha(500, "identity.desconocido").titulo).toBe(
      "No se ha podido cargar la ficha",
    );
  });
});

describe("clasificarInvitacion", () => {
  it("expirada con 410 o identity.invitacion_expirada", () => {
    const [icono, titulo, , clase] = clasificarInvitacion(
      410,
      "identity.invitacion_expirada",
      "",
    );
    expect(icono).toBe("⏰");
    expect(titulo).toBe("La invitación ha expirado");
    expect(clase).toBe("err");
    expect(clasificarInvitacion(410, "", "")[1]).toBe("La invitación ha expirado");
  });

  it("ya usada, no autorizada, no encontrada y camarero ausente", () => {
    expect(clasificarInvitacion(409, "identity.invitacion_ya_usada", "")[1]).toBe(
      "La invitación ya se ha usado",
    );
    expect(
      clasificarInvitacion(403, "identity.invitacion_no_autorizada", "")[1],
    ).toBe("No autorizado");
    expect(
      clasificarInvitacion(404, "identity.invitacion_no_encontrada", "")[1],
    ).toBe("Invitación no encontrada");
    expect(
      clasificarInvitacion(404, "identity.camarero_no_encontrado", "")[1],
    ).toBe("Cuenta no encontrada");
  });
});

describe("mensajeLogin", () => {
  it("401 o credenciales inválidas piden email y contraseña", () => {
    expect(mensajeLogin(401, "identity.credenciales_invalidas", "")).toBe(
      "Email o contraseña incorrectos.",
    );
  });

  it("409 o clave revocada pide renovar en Commander", () => {
    expect(mensajeLogin(409, "identity.credential_revoked", "")).toContain(
      "Personal Comander",
    );
  });

  it("429 usa el detalle de la API o el texto por defecto", () => {
    expect(mensajeLogin(429, "identity.rate_limited", "Espera 30 s.")).toBe(
      "Espera 30 s.",
    );
    expect(mensajeLogin(429, "identity.rate_limited", "")).toContain(
      "Demasiados intentos",
    );
  });
});
