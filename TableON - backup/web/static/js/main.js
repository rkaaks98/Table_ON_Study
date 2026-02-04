let doc = document.documentElement;

function openFullScreenMode() {
    if (doc.requestFullscreen)
        doc.requestFullscreen();
    else if (doc.webkitRequestFullscreen) // Chrome, Safari (webkit)
        doc.webkitRequestFullscreen();
    else if (doc.mozRequestFullScreen) // Firefox
        doc.mozRequestFullScreen();
    else if (doc.msRequestFullscreen) // IE or Edge
        doc.msRequestFullscreen();
    document.getElementById('fullscreen').remove();
}

function addOrder(btn) {
    let btnNum = btn.id.match(/\d+/)[0];
    if (document.getElementById('menuBox_' + btnNum) == null) {
        let menuName = btn.querySelector('input').value;
        let parentDiv = document.getElementById("scl");
        let newDiv = document.createElement("div");
        newDiv.id = "menuBox_" + btnNum;

        newDiv.innerHTML = `
        <div class="row">
            <div class="order-list-info">
                <div class="order-background">
                    <div class="col-md-3">
                        <img class="order-menu-img" src="/static/image/`+ btnNum + `.png" alt="">
                    </div>
                    <div class="col-md-3 order-info">
                        <p id="menu_name`+ btnNum + `">` + menuName + `</p>
                    </div>
                    <div class="col-md-3">
                        
                    </div>
                    <div class="col-md-3">
                        <img id="delete_`+ btnNum + `" class="delete" src="/static/img/delete.png" onclick="deleteOrder(this.id)">
                    </div>
                </div>
            </div>
        </div>
        `;

        parentDiv.appendChild(newDiv);
    }
}

function deleteOrder(btn) {
    let number = btn.match(/\d+/)[0];
    document.getElementById('menuBox_' + number).remove();
}




let menu = [];
let menuCode = [];
let orderCode = 100;

function orderCheck() {
    let orderList = document.getElementById('scl').children;
    document.getElementById('order_check').replaceChildren();
    menuCode = [];
    
    for (let i = 0; i < orderList.length; i++) {
        document.getElementById('order_num').textContent = '# 주문번호 - ' + orderCode
        let number = orderList[i].id.match(/\d+/)[0];
        menu[i] = document.getElementById('menu_name' + number).textContent;
        menuCode[i] = number;
        
        let p_tag = document.createElement('p');
        p_tag.innerText = '#' + (i + 1) + " " + menu[i];
        document.getElementById('order_check').appendChild(p_tag);
    }

    if (orderList.length > 0) {
        $('#orderModal').modal('show');
    }
}

function requestOrder() {

    console.log(menuCode);
    for (let i = 0; i < menuCode.length; i++) {
        axios.get('http://192.168.0.4:8100/addOrder/' + orderCode + "/" + menuCode[i] + "/" + 1)
            .then(response => {
                console.log(response)
                $('#orderModal').modal('hide');
                document.getElementById('scl').replaceChildren();
            })
            .catch(error => {
                console.error('요청 실패', error);
            });
    }
    orderCode++;
}