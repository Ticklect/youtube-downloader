// Chrome storage writes are asynchronous. Preserve the order of rapid edits so
// a slow earlier write cannot overwrite a newer selection or preference.
export function createStorageQueue(write) {
  let pending = Promise.resolve();

  return function enqueue(snapshot) {
    const operation = pending.then(() => write(snapshot));
    pending = operation.catch(() => {});
    return operation;
  };
}
