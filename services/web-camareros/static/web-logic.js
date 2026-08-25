(function (root) {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function clasificarFicha(status, code) {
    if (code === "identity.qr_invalido" || status === 422) {
      return {
        icono: "⚠️",
        titulo: "QR no válido",
        detalle: "Este código no es un QR de profesional válido. Comprueba que el enlace está completo.",
        clase: "err",
      };
    }
    if (code === "identity.credencial_inactiva" || status === 409) {
      return {
        icono: "🚫",
        titulo: "Credencial no activa",
        detalle: "La clave de este QR ha sido revocada o renovada. Pide al profesional su QR actualizado.",
        clase: "err",
      };
    }
    return {
      icono: "⚠️",
      titulo: "No se ha podido cargar la ficha",
      detalle: "Ocurrió un error. Inténtalo de nuevo más tarde.",
      clase: "err",
    };
  }

  var invitacionPorCodigo = {
    "identity.invitacion_expirada": ["⏰", "La invitación ha expirado",
      "Este enlace ya no es válido. Pide al responsable del establecimiento que te envíe una nueva invitación.", "err"],
    "identity.invitacion_ya_usada": ["🔁", "La invitación ya se ha usado",
      "Este enlace ya fue utilizado o revocado. Si crees que es un error, contacta con el establecimiento.", "warn"],
    "identity.invitacion_no_autorizada": ["🚫", "No autorizado",
      "La invitación no corresponde a tu cuenta. Entra con el email al que se envió la invitación.", "err"],
    "identity.invitacion_no_encontrada": ["❓", "Invitación no encontrada",
      "No existe una invitación para este enlace. Comprueba que el enlace está completo.", "err"],
    "identity.camarero_no_encontrado": ["👤", "Cuenta no encontrada",
      "No existe una cuenta de profesional para el email de la invitación. Regístrate primero en Personal Hostel.", "warn"],
  };
  var invitacionPorStatus = {
    410: invitacionPorCodigo["identity.invitacion_expirada"],
    409: invitacionPorCodigo["identity.invitacion_ya_usada"],
    403: invitacionPorCodigo["identity.invitacion_no_autorizada"],
    404: invitacionPorCodigo["identity.invitacion_no_encontrada"],
  };

  function clasificarInvitacion(status, code, detalle) {
    return invitacionPorCodigo[code] || invitacionPorStatus[status] || ["⚠️", "No se ha podido completar",
      detalle || "Ocurrió un error al procesar la invitación. Inténtalo de nuevo más tarde.", "err"];
  }

  function mensajeLogin(status, code, detail) {
    if (code === "identity.credential_revoked" || status === 409) {
      return "Tu cuenta no tiene una clave activa. Renueva la clave desde tu app (Personal Comander).";
    }
    if (code === "identity.rate_limited" || status === 429) {
      return detail || "Demasiados intentos. Espera un momento e inténtalo de nuevo.";
    }
    return "Email o contraseña incorrectos.";
  }

  var api = {
    esc: esc,
    clasificarFicha: clasificarFicha,
    clasificarInvitacion: clasificarInvitacion,
    mensajeLogin: mensajeLogin,
  };
  root.PhWebLogic = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
