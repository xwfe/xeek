// 同源 iframe 里的第二个写者：和另一个标签一样有独立的连接和锁请求，不用驱动也能测并发。
import * as cache from "./cipher-cache.js";

window.cache = cache;
parent.postMessage("frame-ready", location.origin);
