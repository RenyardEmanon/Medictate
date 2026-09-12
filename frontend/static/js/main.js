// Small fetch wrapper used by signup.html / login.html.
// Sends JSON, includes the session cookie, and throws a readable Error
// on non-2xx responses so callers can just do: catch (err) { ... err.message }
async function apiFetch(path, options = {}) {
  console.log("[apiFetch] calling:", path, options);
  try {
    const res = await fetch(path, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      credentials: "include", // send/receive the Flask-Login session cookie
      body: options.body,
    });

    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      // no JSON body (e.g. a 500 with an HTML error page) — leave data = {}
    }

    console.log("[apiFetch] response:", res.status, data);

    if (!res.ok) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }

    return data;
  } catch (err) {
    console.error("[apiFetch] FAILED:", err);
    // Re-throw a readable message even for network-level failures
    // (e.g. server not running, wrong port, CORS block)
    if (err instanceof TypeError) {
      throw new Error("Could not reach the server. Is Flask running on the right port?");
    }
    throw err;
  }
}

// Like apiFetch, but for file uploads (multipart/form-data). Don't set
// Content-Type manually — the browser sets the correct boundary itself.
async function apiUpload(path, formData) {
  const res = await fetch(path, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  let data = {};
  try {
    data = await res.json();
  } catch (_) {}

  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }

  return data;
}

// Shows a message under a form ("error" or "success").
function showMsg(el, text, type = "error") {
  el.textContent = text;
  el.className = `msg ${type}`;
}

console.log("[main.js] loaded successfully");
