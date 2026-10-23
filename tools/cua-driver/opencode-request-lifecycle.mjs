// One owner for outstanding driver requests. A deadline reports uncertainty;
// it never retries an input whose side effects may already have occurred.
export class RequestDeadlines {
  constructor({onTimeout, setTimer = setTimeout, clearTimer = clearTimeout} = {}) {
    this.requests = new Map();
    this.onTimeout = onTimeout;
    this.setTimer = setTimer;
    this.clearTimer = clearTimer;
  }
  get size() { return this.requests.size; }
  get atCapacity() { return this.size >= 128; }
  has(id) { return this.requests.has(id); }
  ids() { return this.requests.keys(); }
  watch(id, method) {
    if (this.has(id) || this.atCapacity) throw new Error('Driver request already pending or capacity reached');
    const timer = this.setTimer(() => {
      if (this.requests.get(id) === timer) this.onTimeout(id, method);
    }, method === 'initialize' ? 20000 : 120000);
    this.requests.set(id, timer);
  }
  complete(id) {
    if (!this.has(id)) return;
    this.clearTimer(this.requests.get(id));
    this.requests.delete(id);
  }
  close() { for (const id of this.ids()) this.complete(id); }
}
