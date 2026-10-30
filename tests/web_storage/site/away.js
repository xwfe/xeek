// 给 BFCache 留出存入的时间再返回；?stay 时留在这里，由驱动决定什么时候返回。
if (!new URLSearchParams(location.search).has("stay")) setTimeout(() => history.back(), 300);
