// Small IndexedDB wrapper. "kv" holds cached site data and drafts; "outbox"
// holds finished records that wait for a signal.
const IDB = (() => {
  let dbp = null;
  function open() {
    if (dbp) return dbp;
    dbp = new Promise((res, rej) => {
      const r = indexedDB.open("sitesafe", 1);
      r.onupgradeneeded = () => {
        const db = r.result;
        if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
        if (!db.objectStoreNames.contains("outbox")) db.createObjectStore("outbox", { keyPath: "id" });
      };
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
    return dbp;
  }
  async function tx(store, mode, fn) {
    const db = await open();
    return new Promise((res, rej) => {
      const t = db.transaction(store, mode), s = t.objectStore(store);
      const out = fn(s);
      t.oncomplete = () => res(out && "result" in out ? out.result : out);
      t.onerror = () => rej(t.error);
      t.onabort = () => rej(t.error);
    });
  }
  return {
    get: (k) => tx("kv", "readonly", (s) => s.get(k)),
    set: (k, v) => tx("kv", "readwrite", (s) => s.put(v, k)),
    del: (k) => tx("kv", "readwrite", (s) => s.delete(k)),
    outbox: {
      all: () => tx("outbox", "readonly", (s) => s.getAll()),
      put: (item) => tx("outbox", "readwrite", (s) => s.put(item)),
      del: (id) => tx("outbox", "readwrite", (s) => s.delete(id)),
    },
  };
})();
