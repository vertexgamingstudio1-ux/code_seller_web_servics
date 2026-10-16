const API="https://code-seller-web-servics.onrender.com/api";
const CART_KEY="code_seller_cart";
const USER_KEY="code_seller_user";
const ORDERS_KEY="code_seller_orders";
const WISH_KEY="code_seller_wishlist";
const PRODUCTS=[
{id:"code-001",name:"AI Starter Project",category:"AI",description:"Complete starter project for building an AI application.",price:999,badge:"Featured"},
{id:"code-002",name:"Modern Web Starter",category:"Web",description:"A clean foundation for a modern web project.",price:699,badge:"Popular"},
{id:"code-003",name:"Game Development Kit",category:"Games",description:"Starter source code for your next game project.",price:1299,badge:"New"},
{id:"code-004",name:"Developer Utility",category:"Tools",description:"A useful free tool for developers.",price:0,badge:"Free"},
{id:"code-005",name:"Python Automation Pack",category:"Python",description:"Automation scripts and useful Python utilities.",price:799,badge:""},
{id:"code-006",name:"JavaScript Dashboard",category:"Web",description:"Reusable dashboard components for JavaScript projects.",price:1099,badge:"Best Seller"}
];
function read(k,f){try{return JSON.parse(localStorage.getItem(k))??f}catch{return f}}
function write(k,v){localStorage.setItem(k,JSON.stringify(v))}
function getCart(){return read(CART_KEY,[])}
function getUser(){return read(USER_KEY,null)}
function getOrders(){return read(ORDERS_KEY,[])}
function getWishlist(){return read(WISH_KEY,[])}
function product(id){return PRODUCTS.find(p=>p.id===id)}
function money(v){return Number(v||0)===0?"FREE":"₹"+Number(v).toLocaleString("en-IN")}
function cartCount(){return getCart().reduce((n,x)=>n+Number(x.qty||0),0)}
function cartTotal(){return getCart().reduce((n,x)=>n+(product(x.id)?.price||0)*Number(x.qty||0),0)}
function updateHeader(){
 const count=document.getElementById("cartCount");
 if(count)count.textContent=cartCount();
 const user=getUser();
 document.querySelectorAll(".header-link").forEach(a=>{
   if(a) a.textContent=user?"Account":"Sign in";
   if(a)a.href=user?"account.html":"login.html";
 });
}
function addToCart(id){
 const p=product(id); if(!p)return;
 const cart=getCart();
 const item=cart.find(x=>x.id===id);
 if(item)item.qty++;
 else cart.push({id,qty:1});
 write(CART_KEY,cart);
 updateHeader();
 document.querySelectorAll('[data-id="'+id+'"]').forEach(b=>{
   const old=b.textContent;b.textContent="Added ✓";
   setTimeout(()=>b.textContent=old,900);
 });
}
function removeFromCart(id){write(CART_KEY,getCart().filter(x=>x.id!==id));renderCart();updateHeader()}
function changeQty(id,d){
 const cart=getCart();const item=cart.find(x=>x.id===id);
 if(!item)return;
 item.qty=Math.max(1,Number(item.qty)+d);
 write(CART_KEY,cart);renderCart();updateHeader();
}
function renderCart(){
 const box=document.getElementById("cartItems");
 const total=document.getElementById("cartTotal");
 const count=document.getElementById("cartItemCount");
 if(!box)return;
 const cart=getCart();
 if(count)count.textContent=cartCount();
 if(!cart.length){
   box.innerHTML='<div class="empty-state"><h3>Your cart is empty</h3><p>Add some code from the Shop.</p><a class="primary-button" href="shop.html">Continue shopping</a></div>';
   if(total)total.textContent=money(0);
   return;
 }
 box.innerHTML=cart.map(x=>{
   const p=product(x.id);if(!p)return "";
   return '<div class="cart-item"><div class="cart-item-icon">'+p.category+'</div><div class="cart-item-info"><span class="eyebrow">'+p.category+'</span><h3>'+p.name+'</h3><p>'+p.description+'</p><div class="quantity-controls"><button data-minus="'+p.id+'">−</button><strong>'+x.qty+'</strong><button data-plus="'+p.id+'">+</button><button class="remove-item" data-remove="'+p.id+'">Remove</button></div></div><strong class="cart-item-price">'+money(p.price*x.qty)+'</strong></div>';
 }).join("");
 box.querySelectorAll("[data-minus]").forEach(b=>b.onclick=()=>changeQty(b.dataset.minus,-1));
 box.querySelectorAll("[data-plus]").forEach(b=>b.onclick=()=>changeQty(b.dataset.plus,1));
 box.querySelectorAll("[data-remove]").forEach(b=>b.onclick=()=>removeFromCart(b.dataset.remove));
 if(total)total.textContent=money(cartTotal());
}
function renderShop(){
 const grid=document.getElementById("productGrid");if(!grid)return;
 const q=(document.getElementById("shopSearch")?.value||"").toLowerCase();
 const cat=new URLSearchParams(location.search).get("category");
 const list=PRODUCTS.filter(p=>(!cat||p.category.toLowerCase()===cat.toLowerCase())&&(!q||(p.name+" "+p.category+" "+p.description).toLowerCase().includes(q)));
 grid.innerHTML=list.map(p=>'<article class="product-card"><span class="eyebrow">'+p.category+'</span><h3>'+p.name+'</h3><p>'+p.description+'</p><div class="product-bottom"><strong>'+money(p.price)+'</strong><button class="add-cart" data-id="'+p.id+'">Add to Cart</button></div></article>').join("");
 grid.querySelectorAll(".add-cart").forEach(b=>b.onclick=()=>addToCart(b.dataset.id));
 const meta=document.getElementById("shopMeta");if(meta)meta.textContent=list.length+" product"+(list.length===1?"":"s")+" available";
}
function renderWishlist(){
 const box=document.getElementById("wishlistGrid");if(!box)return;
 const ids=getWishlist();
 const list=ids.map(product).filter(Boolean);
 if(!list.length){box.innerHTML='<div class="empty-state"><h3>Your wishlist is empty</h3><p>Save products you want to come back to.</p></div>';return}
 box.innerHTML=list.map(p=>'<article class="product-card"><span class="eyebrow">'+p.category+'</span><h3>'+p.name+'</h3><p>'+p.description+'</p><div class="product-bottom"><strong>'+money(p.price)+'</strong><div><button class="add-cart" data-id="'+p.id+'">Add to Cart</button><button class="secondary remove-wish" data-wish="'+p.id+'">Remove</button></div></div></article>').join("");
 box.querySelectorAll(".add-cart").forEach(b=>b.onclick=()=>addToCart(b.dataset.id));
 box.querySelectorAll(".remove-wish").forEach(b=>b.onclick=()=>{write(WISH_KEY,getWishlist().filter(x=>x!==b.dataset.wish));renderWishlist()});
}
function checkout(){
 const user=getUser();
 if(!user){location.href="login.html?return=checkout.html";return}
 const cart=getCart();
 if(!cart.length){location.href="cart.html";return}
 const order={id:"CS-"+Date.now().toString().slice(-8),date:new Date().toISOString(),status:"Paid",total:cartTotal(),items:cart.map(x=>({...x,name:product(x.id)?.name}))};
 const orders=getOrders();orders.unshift(order);write(ORDERS_KEY,orders);write(CART_KEY,[]);
 location.href="orders.html";
}
function renderOrders(){
 const box=document.getElementById("ordersList");if(!box)return;
 const user=getUser();
 if(!user){box.innerHTML='<div class="empty-state"><h3>Sign in to view orders</h3><a class="primary-button" href="login.html">Sign in</a></div>';return}
 const orders=getOrders();
 if(!orders.length){box.innerHTML='<div class="empty-state"><h3>No orders yet</h3><p>Your purchased code will appear here.</p><a class="primary-button" href="shop.html">Shop now</a></div>';return}
 box.innerHTML=orders.map(o=>'<article class="product-card"><span class="eyebrow">ORDER '+o.id+'</span><h3>'+new Date(o.date).toLocaleString()+'</h3><p>Status: <strong>'+o.status+'</strong></p><p>Items: '+o.items.map(i=>i.name+" × "+i.qty).join(", ")+'</p><div class="product-bottom"><strong>'+money(o.total)+'</strong><a class="primary-button" href="downloads.html">Downloads</a></div></article>').join("");
}
function renderDownloads(){
 const box=document.getElementById("downloadsList");if(!box)return;
 const user=getUser();
 if(!user){box.innerHTML='<div class="empty-state"><h3>Sign in to view downloads</h3><a class="primary-button" href="login.html">Sign in</a></div>';return}
 const orders=getOrders();
 const items=[];
 orders.forEach(o=>o.items.forEach(i=>items.push({name:i.name,id:i.id,order:o.id})));
 if(!items.length){box.innerHTML='<div class="empty-state"><h3>No downloads available</h3><p>Purchase a product first.</p></div>';return}
 box.innerHTML=items.map(i=>'<article class="product-card"><span class="eyebrow">PURCHASED CODE</span><h3>'+i.name+'</h3><p>Order '+i.order+'</p><button class="primary-button" type="button" data-download="'+i.id+'">Download</button></article>').join("");
 box.querySelectorAll("[data-download]").forEach(b=>b.onclick=()=>alert("Download access will be connected to the protected customer download API."));
}
function renderAccount(){
 const box=document.getElementById("accountContent");if(!box)return;
 const user=getUser();
 if(!user){box.innerHTML='<div class="empty-state"><h3>You are not signed in</h3><a class="primary-button" href="login.html">Sign in</a></div>';return}
 box.innerHTML='<div class="product-card"><span class="eyebrow">ACCOUNT</span><h2>'+String(user.name||"Customer")+'</h2><p>Email: '+String(user.email||"")+'</p><p>Phone: '+String(user.phone||"")+'</p><button id="logoutBtn" class="secondary" type="button">Sign out</button></div>';
 document.getElementById("logoutBtn").onclick=()=>{localStorage.removeItem(USER_KEY);location.href="index.html"};
}
function saveAuthenticatedUser(data) {
  if (!data || !data.success || !data.token || !data.customer) {
    throw new Error(data?.error || "Authentication failed.");
  }
  const customer = data.customer;
  localStorage.setItem("code_seller_token", data.token);
  write(USER_KEY, {
    id: customer.id,
    name: customer.display_name || customer.name || "Customer",
    email: customer.email || "",
    role: customer.role || "customer"
  });
}
async function postAuth(path, body) {
  const response = await fetch(`${API}/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.success) {
    throw new Error(data.error || `Request failed (${response.status}).`);
  }
  return data;
}
window.handleGoogleCredential = async function (response) {
  const message = document.getElementById("googleLoginMessage");
  if (message) message.textContent = "Signing in with Google…";
  try {
    const data = await postAuth("google", { credential: response.credential });
    saveAuthenticatedUser(data);
    if (message) message.textContent = "Signed in successfully.";
    updateHeader();
    location.href = new URLSearchParams(location.search).get("return") || "account.html";
  } catch (error) {
    if (message) message.textContent = error.message || "Google sign-in failed.";
  }
};
function initGoogleSignIn() {
  const target = document.getElementById("googleSignInButton");
  if (!target || !window.google?.accounts?.id) return;
  google.accounts.id.initialize({
    client_id: "189197583620-ilsns5f5hqf4af2q37gnko5bniq1c8hc.apps.googleusercontent.com",
    callback: window.handleGoogleCredential
  });
  google.accounts.id.renderButton(target, {
    theme: "outline",
    size: "large",
    text: "signin_with",
    shape: "rectangular",
    width: Math.min(320, target.parentElement.clientWidth || 320)
  });
}
function setupAuth() {
  const lf = document.getElementById("loginForm");
  if (lf) lf.onsubmit = async e => {
    e.preventDefault();
    const email = document.getElementById("loginIdentity")?.value.trim();
    const password = document.getElementById("loginPassword")?.value;
    const msg = document.getElementById("loginMessage");
    if (!email || !password) {
      if (msg) msg.textContent = "Enter your email and password.";
      return;
    }
    if (msg) msg.textContent = "Signing in…";
    try {
      const data = await postAuth("login", { email, password });
      saveAuthenticatedUser(data);
      if (msg) msg.textContent = "Signed in.";
      updateHeader();
      location.href = new URLSearchParams(location.search).get("return") || "account.html";
    } catch (error) {
      if (msg) msg.textContent = error.message || "Sign-in failed.";
    }
  };
  const rf = document.getElementById("registerForm");
  if (rf) rf.onsubmit = async e => {
    e.preventDefault();
    const name = document.getElementById("registerName")?.value.trim();
    const email = document.getElementById("registerEmail")?.value.trim();
    const password = document.getElementById("registerPassword")?.value;
    const msg = document.getElementById("registerMessage");
    if (!name || !email || !password) {
      if (msg) msg.textContent = "Enter your name, email and password.";
      return;
    }
    if (msg) msg.textContent = "Creating account…";
    try {
      const data = await postAuth("register", {
        display_name: name, email, password
      });
      saveAuthenticatedUser(data);
      if (msg) msg.textContent = "Account created.";
      updateHeader();
      location.href = "account.html";
    } catch (error) {
      if (msg) msg.textContent = error.message || "Registration failed.";
    }
  };
  initGoogleSignIn();
  if (document.getElementById("googleSignInButton") && !window.google?.accounts?.id) {
    const script = document.querySelector('script[src*="accounts.google.com/gsi/client"]');
    script?.addEventListener("load", initGoogleSignIn, { once: true });
  }
}
function setupMenu(){
 const menu=document.getElementById("menuBtn"),close=document.getElementById("closeMenu"),side=document.getElementById("sidebar"),overlay=document.getElementById("overlay");
 if(!menu||!side)return;
 const open=()=>{side.classList.add("open");overlay?.classList.add("show")};
 const shut=()=>{side.classList.remove("open");overlay?.classList.remove("show")};
 menu.onclick=e=>{e.preventDefault();open()};
 close?.addEventListener("click",shut);overlay?.addEventListener("click",shut);
 document.addEventListener("keydown",e=>{if(e.key==="Escape")shut()});
}
function setupSearch(){
 const input=document.getElementById("searchInput"),btn=document.getElementById("searchBtn");
 const go=()=>{const q=input?.value.trim();if(q)location.href="shop.html?search="+encodeURIComponent(q);};
 btn?.addEventListener("click",go);input?.addEventListener("keydown",e=>{if(e.key==="Enter")go()});
 const shop=document.getElementById("shopSearch");
 shop?.addEventListener("input",renderShop);
}
document.addEventListener("DOMContentLoaded",()=>{
 updateHeader();setupMenu();setupSearch();setupAuth();renderCart();renderShop();renderWishlist();renderOrders();renderDownloads();renderAccount();
 document.querySelectorAll(".add-cart").forEach(b=>b.addEventListener("click",()=>addToCart(b.dataset.id)));
 document.getElementById("checkoutBtn")?.addEventListener("click",checkout);
});

