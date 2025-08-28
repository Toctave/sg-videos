const table = document.getElementById("table").getElementsByTagName("tbody")[0];

data.map((e, i) => {
  const keys = [e.title, e.type].concat(e.presenters);
  e.searchKeys = keys.map((k) => k.toLowerCase());
});

// For sorting ascending or descending 
const sortDescending = { date: false, title: false, presenters: false, type: false }; 

// To create table 
function addItem(e, i) { 
  let row = table.insertRow(); 
  let cDate = row.insertCell();
  let cTitle = row.insertCell();
  let cTyp = row.insertCell();
  let cPresenters = row.insertCell();

  cDate.innerText = e.start_mdt + ' - ' + e.end_mdt;

  if (e.video_file_path.length > 0) {
    let videoLink = document.createElement('a');
    videoLink.href = e.video_file_path;
    videoLink.innerText = e.title;
    cTitle.appendChild(videoLink);
  } else {
    cTitle.innerText = e.title;
  }
  cPresenters.innerText = e.presenters;
  cTyp.innerText = e.type;
} 

// Traverse and insert items to table 
data.map((e, i) => addItem(e, i)); 

// For sorting in different cases 
function sortItems(key) { 
  remove();

  data.sort((a, b) => {
    if (a[key] < b[key]) {
      return -1;
    } else if (a[key] > b[key]) {
      return 1;
    } else {
      return 0;
    }
  });
  
  if (sortDescending[key]) {
    data.reverse();
  }
  sortDescending[key] = !sortDescending[key];
  
  data.map((e, i) => addItem(e, i));
} 

// Clear the table before updation 
function remove() { 
  while (table.rows.length > 0) table.deleteRow(-1); 
} 

// To search and filter items 
function searchItems() { 
  let input = document 
    .getElementById("searchInput") 
    .value.toLowerCase(); 
  let filterItems = data.filter((e) => { 
    return e.searchKeys.some((key) => key.includes(input));
  }); 

  remove(); 
  filterItems.map((e, i) => addItem(e, i)); 
} 
