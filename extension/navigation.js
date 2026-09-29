export async function openOrFocusDownloader(chromeApi) {
  const targetUrl = chromeApi.runtime.getURL("downloader.html");

  let tabs = [];
  try {
    tabs = await chromeApi.tabs.query({ url: targetUrl });
  } catch {
    tabs = [];
  }

  const existing = Array.isArray(tabs)
    ? tabs.find((tab) => tab?.url === targetUrl && Number.isInteger(tab.id))
    : undefined;

  if (existing) {
    await chromeApi.tabs.update(existing.id, { active: true });
    if (Number.isInteger(existing.windowId) && chromeApi.windows?.update) {
      await chromeApi.windows.update(existing.windowId, { focused: true });
    }
    return { action: "focused", tabId: existing.id };
  }

  const created = await chromeApi.tabs.create({ url: targetUrl });
  return Number.isInteger(created?.id)
    ? { action: "created", tabId: created.id }
    : { action: "created" };
}
