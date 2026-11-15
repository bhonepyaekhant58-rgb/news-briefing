(function () {
  "use strict";

  const config = JSON.parse(document.getElementById("config").textContent);
  const KEY_NAME = "briefing-access-key";
  const PENDING_NAME = "briefing-pending";
  const MAX_TOPICS = 20;
  const WAIT_LIMIT = 10 * 60 * 1000;
  const api = "https://api.github.com/repos/" + config.repo + "/contents/settings.json";
  const $ = (id) => document.getElementById(id);

  let settings = null;  // the saved settings file, as last read
  let fileSha = "";     // the file's version id, needed to save over it
  let draft = [];       // the topic list being edited in the picker
  let timer = null;

  function read(name) {
    try { return localStorage.getItem(name); } catch (error) { return null; }
  }

  function store(name, value) {
    try {
      if (value === null) localStorage.removeItem(name); else localStorage.setItem(name, value);
    } catch (error) { /* private browsing: carry on without remembering */ }
  }

  const lower = (name) => name.trim().toLowerCase();
  const nameOf = (entry) => (typeof entry === "string" ? entry : entry.name);

  // Must match topics_key() in briefing/config.py.
  function topicsKey(topics) {
    return topics.map((topic) => lower(topic.name) + ":" + (topic.priority || "normal")).join("|");
  }

  function notice(text) {
    $("notice").textContent = text;
    $("notice").hidden = !text;
  }

  function say(text) {
    $("picker-message").textContent = text;
    $("picker-message").hidden = !text;
  }

  // Show only the sections and menu links whose topic is still in the list.
  function hideRemoved(topics) {
    const names = topics.map((topic) => lower(topic.name));
    document.querySelectorAll("[data-topic]").forEach((element) => {
      element.hidden = !names.includes(element.dataset.topic);
    });
  }

  function decode(base64) {
    const bytes = Uint8Array.from(atob(base64.replace(/\s/g, "")), (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }

  function encode(text) {
    let binary = "";
    new TextEncoder().encode(text).forEach((byte) => { binary += String.fromCharCode(byte); });
    return btoa(binary);
  }

  // Reading needs no key, because the repository is public.
  async function loadSettings() {
    const response = await fetch(api + "?ref=main", {
      headers: { Accept: "application/vnd.github+json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Could not read the saved topics (error " + response.status + ").");
    const file = await response.json();
    fileSha = file.sha;
    settings = JSON.parse(decode(file.content));
  }

  function saveSettings(key) {
    return fetch(api, {
      method: "PUT",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: "Bearer " + key,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: "Update topics from the page",
        content: encode(JSON.stringify(settings, null, 2) + "\n"),
        sha: fileSha,
        branch: "main",
      }),
    });
  }

  // Check every 20 seconds until the published page was built from this topic list.
  function watchForUpdate(key, since) {
    clearInterval(timer);
    notice("Updating your briefing. This usually takes about 5 minutes.");
    async function check() {
      if (Date.now() - since > WAIT_LIMIT) {
        clearInterval(timer);
        notice("The update did not finish. Your topics are saved and the next build will use them.");
        return;
      }
      try {
        const status = await (await fetch("status.json", { cache: "no-store" })).json();
        if (status.topics_key === key) {
          clearInterval(timer);
          store(PENDING_NAME, null);
          location.replace(location.pathname + "?v=" + Date.now());
        }
      } catch (error) { /* try again on the next check */ }
    }
    timer = setInterval(check, 20000);
    check();
  }

  // Suggestions, plus saved topics removed in this session, so they can be put back.
  function offered() {
    const seen = [];
    return (settings.suggested || []).concat(settings.topics).filter((entry) => {
      const name = lower(nameOf(entry));
      if (seen.includes(name)) return false;
      seen.push(name);
      return true;
    });
  }

  function renderPicker() {
    const chosen = $("chosen");
    chosen.textContent = "";
    draft.forEach((topic, index) => {
      const row = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = topic.name;
      const star = document.createElement("button");
      star.type = "button";
      star.textContent = topic.priority === "high" ? "★ High priority" : "☆ Normal";
      star.setAttribute("aria-pressed", String(topic.priority === "high"));
      star.addEventListener("click", () => {
        topic.priority = topic.priority === "high" ? "normal" : "high";
        renderPicker();
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", "Remove " + topic.name);
      remove.addEventListener("click", () => {
        draft.splice(index, 1);
        say("");
        renderPicker();
      });
      row.append(label, star, remove);
      chosen.append(row);
    });

    const names = draft.map((topic) => lower(topic.name));
    const list = $("suggested");
    list.textContent = "";
    offered().filter((entry) => !names.includes(lower(nameOf(entry)))).forEach((entry) => {
      const row = document.createElement("li");
      const add = document.createElement("button");
      add.type = "button";
      add.textContent = "+ " + nameOf(entry);
      add.addEventListener("click", () => addTopic(nameOf(entry)));
      row.append(add);
      list.append(row);
    });
  }

  function addTopic(rawName) {
    const name = rawName.trim().replace(/\s+/g, " ");
    if (!name) return say("Type a topic name first.");
    if (draft.some((topic) => lower(topic.name) === lower(name))) {
      return say("\"" + name + "\" is already one of your topics.");
    }
    if (draft.length >= MAX_TOPICS) {
      return say("You can have at most " + MAX_TOPICS + " topics. Remove one first.");
    }
    // A known topic keeps its feeds and icon; a new one is searched by its name.
    const known = offered().find((entry) => lower(nameOf(entry)) === lower(name));
    if (known && typeof known === "object") {
      draft.push(Object.assign({}, known, { priority: "normal" }));
    } else {
      draft.push({ name: nameOf(known || name), priority: "normal" });
    }
    $("new-topic").value = "";
    say("");
    renderPicker();
  }

  // Copy the edited list into the settings. A removed topic that has its own feeds
  // is kept under "suggested", so it can be added back later without losing them.
  function applyDraft() {
    const keep = draft.map((topic) => lower(topic.name));
    const suggested = (settings.suggested || []).slice();
    const listed = suggested.map((entry) => lower(nameOf(entry)));
    settings.topics.forEach((topic) => {
      const configured = Object.keys(topic).some((field) => field !== "name" && field !== "priority");
      if (configured && !keep.includes(lower(topic.name)) && !listed.includes(lower(topic.name))) {
        suggested.push(Object.assign({}, topic, { priority: "normal" }));
      }
    });
    settings.suggested = suggested;
    settings.topics = draft.map((topic) => Object.assign({}, topic));
  }

  async function save() {
    if (!draft.length) return say("Keep at least 1 topic.");
    if (draft.length > MAX_TOPICS) return say("You can have at most " + MAX_TOPICS + " topics.");
    const key = read(KEY_NAME) || $("key").value.trim();
    if (!key) {
      $("key-row").hidden = false;
      return say("Paste your access key to save. It is kept on this device only.");
    }
    const before = { topics: settings.topics, suggested: settings.suggested };
    const undo = () => {
      settings.topics = before.topics;
      settings.suggested = before.suggested;
    };
    applyDraft();
    say("Saving…");
    let response;
    try {
      response = await saveSettings(key);
      if (response.status === 409) {  // the file changed since it was read: read it again, retry once
        await loadSettings();
        applyDraft();
        response = await saveSettings(key);
      }
    } catch (error) {
      undo();
      return say("Could not reach GitHub. Check your connection and try again.");
    }
    if (response.status === 401 || response.status === 403 || response.status === 404) {
      undo();
      store(KEY_NAME, null);
      $("key").value = "";
      $("key-row").hidden = false;
      $("forget-key").hidden = true;
      return say("That access key was not accepted. Paste a new one. Your saved topics are unchanged.");
    }
    if (!response.ok) {
      undo();
      return say("Saving failed (error " + response.status + "). Your saved topics are unchanged.");
    }
    store(KEY_NAME, key);
    fileSha = (await response.json()).content.sha;
    $("picker").close();
    hideRemoved(settings.topics);
    const savedKey = topicsKey(settings.topics);
    if (savedKey === config.builtKey) {  // back to the list the page already shows
      clearInterval(timer);
      store(PENDING_NAME, null);
      notice("");
      return;
    }
    const since = Date.now();
    store(PENDING_NAME, JSON.stringify({ key: savedKey, since: since }));
    watchForUpdate(savedKey, since);
  }

  async function openPicker() {
    if (!config.repo) return notice("Topics can only be changed on the published page.");
    try { await loadSettings(); } catch (error) { return notice(error.message); }
    draft = settings.topics.map((topic) => Object.assign({}, topic));
    const hasKey = Boolean(read(KEY_NAME));
    $("key").value = "";
    $("key-row").hidden = hasKey;
    $("forget-key").hidden = !hasKey;
    say("");
    renderPicker();
    $("picker").showModal();
  }

  // On every page load: say so if the page is old, and notice a topic list saved elsewhere.
  async function start() {
    const today = new Date(Date.now() + 7 * 60 * 60 * 1000).toISOString().slice(0, 10);
    if (config.builtDay !== today) {
      notice("This briefing is from " + config.builtDay + ". Today's has not been built yet.");
    }
    if (!config.repo) return;
    try { await loadSettings(); } catch (error) { return; }
    const savedKey = topicsKey(settings.topics);
    if (savedKey === config.builtKey) {
      store(PENDING_NAME, null);
      return;
    }
    hideRemoved(settings.topics);
    const pending = JSON.parse(read(PENDING_NAME) || "null");
    const since = pending && pending.key === savedKey ? pending.since : Date.now();
    store(PENDING_NAME, JSON.stringify({ key: savedKey, since: since }));
    watchForUpdate(savedKey, since);
  }

  $("open-picker").addEventListener("click", openPicker);
  $("cancel").addEventListener("click", () => $("picker").close());
  $("save").addEventListener("click", save);
  $("add-topic").addEventListener("click", () => addTopic($("new-topic").value));
  $("new-topic").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addTopic($("new-topic").value);
    }
  });
  $("forget-key").addEventListener("click", () => {
    store(KEY_NAME, null);
    $("key-row").hidden = false;
    $("forget-key").hidden = true;
    say("The access key was removed from this device.");
  });

  start();
})();
