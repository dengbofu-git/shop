(function () {
    var checkoutState = {
        settlement_type: 0,
        buy_count: null,
        sku_id: null
    };

    function bindGoPayHandler() {
        if (bindGoPayHandler.done) return;
        bindGoPayHandler.done = true;
        $(document).on('click', '#go_pay', function (e) {
            e.preventDefault();
            var $selected = $('.allAdd_content .base.base_select').first();
            if (!$selected.length) {
                $selected = $('.allAdd_content .base').first();
            }
            if (!$selected.length) {
                alert('请先添加收货地址');
                $('.modal').show();
                return;
            }
            var addressId = $selected.attr('data-id');
            if (!addressId) {
                alert('收货地址无效，请重新选择');
                return;
            }
            var st = checkoutState.settlement_type;
            var url = 'payment.html?address_id=' + encodeURIComponent(addressId) +
                '&settlement_type=' + encodeURIComponent(st);
            if (checkoutState.buy_count && checkoutState.sku_id) {
                url += '&buy_count=' + encodeURIComponent(checkoutState.buy_count) +
                    '&sku_id=' + encodeURIComponent(checkoutState.sku_id);
            }
            window.location.href = url;
        });
    }

    bindGoPayHandler();

function orders() {
                flag = false
                function push_ajax(parameter_url,settlement_type){
                checkoutState.settlement_type = settlement_type;
                $.ajax({
                    type: 'get',
                    url: baseUrl+'/v1/orders/'+username+"/advance"+parameter_url,
                    datatype: 'json',
                    beforeSend:function(request){
                        request.setRequestHeader("authorization",token)
                    },
                    async: false,
                    success: function (response) {
                        var result = JSON.stringify(response)
                        var results = JSON.parse(result)
                        if(results.code == 403){
							alert('用户认证已过期，请重新登录');
							AuthStorage.clear();
							location.href = 'login.html';
                            return;
						}
                        if (results.code !== 200 || !results.data) {
                            alert(results.error || results.errmsg || '加载订单信息失败');
                            return;
                        }
                        console.log(results)
                        if(results.data.addresses.length==0){
                            alert("地址为空,请添加地址")
                            flag = true
                        }
			            var data_goods = results.data.sku_list
			            console.log(data_goods)
                        var data_address = results.data.addresses
                        var buy_count = results.data.buy_count
                        var sku_id = results.data.sku_id
                        checkoutState.buy_count = buy_count;
                        checkoutState.sku_id = sku_id;
                        var orderConfirm = {
                        }
                        var base_url = results.base_url
                        orderConfirm.data = {
                            html_goods: function () {
                                var HTML = '';
                                var sumPrice = 0;
                                for (var i = 0; i < data_goods.length; i++) {
                                    HTML += ' <ul class="item_detail">'
                                    HTML += '<li class="p_info">'
                                    HTML += '<div class="product_name">'
                                    HTML += '<p>'
                                    HTML += data_goods[i].name
                                    HTML += '</p>'
                                    // HTML += '<span>颜色：深空灰</span>'
                                    var saleattr_name = data_goods[i].sku_sale_attr_name
                                    var saleattr_val = data_goods[i].sku_sale_attr_val
                                    for (var j = 0; j < saleattr_name.length; j++){
                                        HTML += '<span>'
                                        HTML += saleattr_name[j]
                                        HTML += ':'
                                        HTML += saleattr_val[j]
                                        HTML += '</span>&nbsp&nbsp'
                                    }
                                    HTML += '</div>'
                                    var imgPath = (data_goods[i].default_image_url && String(data_goods[i].default_image_url).trim()) ? data_goods[i].default_image_url : '';
                                    HTML += '<b><img src="'+ (imgPath ? (base_url + imgPath) : 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7') + '" style="width:100px"/></b>'
                                    HTML += '</li>'
                                    HTML += '<li class="p_price">'
                                    HTML += '<i>皮粉专属价</i>'
                                    HTML += '<br />'
                                    HTML += '<span class="pro_price">￥<span class="ppp_price">' + data_goods[i].price +
                                        '</span></span>'
                                    HTML += '</li>'
                                    HTML += '<li class="p_count"><span>' + data_goods[i].count + '</span></li>'
                                    HTML += '<li class="p_tPrice">￥<span>' + data_goods[i].count * data_goods[i].price + '</span></li>'
                                    HTML += '</ul>'
                                    sumPrice += data_goods[i].count * data_goods[i].price;
                                }
                                $("#count").html(data_goods.length);
                                $(".zj").html(sumPrice);
                                return HTML;
                            },
                            html_address : function() {
                                var HTML = '';
                                HTML += '<p>收货人信息<span class="rt" id="choose">新增收货地址</span></p>'
                                HTML += '<div class="allAdd_content">'
                                console.log(data_address)
                                for (var i = 0; i < data_address.length; i++) {
                                    if (i==0){
                                        HTML += '<div id="addresId1" data-id="'+data_address[i].id+'" class="base base_select">';
                                    }else{
                                        HTML += '<div id="addresId'+(i+1)+'" data-id="'+data_address[i].id+'" class="base">';
                                    }
                                    HTML += '<i class="address_name">';
                                    HTML += data_address[i].name;
                                    HTML += '</i><i class="user_address">';
                                    HTML += data_address[i].address;
                                    HTML += '&nbsp&nbsp';
                                    HTML += data_address[i].mobile;
                                    HTML += '</i><i class="user_site rt">';
                                    HTML += data_address[i].title;
                                    HTML += '</i></div>';
                                }
                                HTML += '</div>';
                                HTML += '<a id="more" href="javascript:;">更多地址 &gt;&gt;</a>';
                                return HTML;
                                },
                            addads: function () {
                                var receiverName = $("#receiverName").val(); // 收件人
                                var receiverState = $("#receiverState").val(); // 省
                                var receiverCity = $("#receiverCity").val(); // 市
                                var receiverDistrict = $("#receiverDistrict").val(); // 区/县
                                var receiverAddress = $("#receiverAddress").val(); //
                                var receiverMobile = $("#receiverMobile").val();
                                var receiverZip = $("#receiverZip").val();
                                var addressName = $("#addressName").val();
                                var id = 0
                                if (receiverName && receiverState && receiverCity && receiverDistrict && receiverAddress &&
                                    receiverMobile) {
                                    $.ajax({
                                        type: 'post',
                                        url: baseUrl + '/v1/users/'+username+'/address',
                                        contentType:'application/json',
                                        datatype: JSON,
                                        beforeSend:function(request){
                                            request.setRequestHeader("authorization",token)
                                        },
                                        data: JSON.stringify({
                                            "receiver": receiverName,
                                            "address": receiverState + receiverCity + receiverDistrict + receiverAddress,
                                            "receiver_phone": receiverMobile,
                                            'postcode': receiverZip,
                                            'tag': addressName
                                        }),
                                        success: function (response) {
                                            if(response.code == 403){
                                                alert('用户认证已过期，请重新登录');
                                                AuthStorage.clear();
                                                location.href = 'login.html'
                                            }
                                            if(response.code==200){
                                                // 添加地址成功
                                                alert('添加地址成功！')
                                                location.reload()
                                                console.log(response.data)
                                                $('.modal').hide()
                                            }else{
                                                alert(response.error.message)
                                            }

                                        },
                                        error: function (err) {
                                            alert('保存失败' + err)
                                        }
                                    })
                                } else {
                                    alert("请将必填信息填写完整");
                                }
                            },
                            initPage: function () {
                                //顶部支付订单背景画布
                                var canvas = document.getElementById("canvas_gray");
                                var cxt = canvas.getContext("2d");
                                var gray = cxt.createLinearGradient(10, 0, 10, 38);
                                gray.addColorStop(0, '#f5f4f5');
                                gray.addColorStop(1, '#e6e6e5');
                                cxt.beginPath();
                                cxt.fillStyle = gray;
                                cxt.moveTo(20, 19);
                                cxt.lineTo(0, 38);
                                cxt.lineTo(0, 0);
                                cxt.fill();
                                cxt.closePath();
                                //顶部确认订单信息背景画布
                                var canvas = document.getElementById("canvas_blue");
                                var cxt = canvas.getContext("2d");
                                var blue = cxt.createLinearGradient(10, 0, 10, 38);
                                blue.addColorStop(0, '#1A5D1A');
                                blue.addColorStop(1, '#1A5D1A');
                                cxt.beginPath();
                                cxt.fillStyle = blue;
                                cxt.moveTo(20, 19);
                                cxt.lineTo(0, 38);
                                cxt.lineTo(0, 0);
                                cxt.fill();
                                cxt.closePath();
                            }
                        }
                        $(function () {
                            //初始化
                            orderConfirm.data.initPage();
                            $(".item_title").after(orderConfirm.data.html_goods());
                            $(".adress_choice").after(orderConfirm.data.html_address());
                            if(flag==true){
                                $(".modal").show();
                            }
                            //点击显示更多地址事件
                            $("#more").click(function () {
                                if ($(this).hasClass("upup")) {
                                    $(".base_select").siblings().hide();
                                    // $(".allAdd_content>div:not(:first-child)").css("display","none");
                                    $("#more").html("更多地址>>");
                                    $(this).removeClass("upup");
                                } else {
                                    $(".base_select").siblings().show();
                                    // $(".allAdd_content>div:not(:first-child)").css("display","block");
                                    $("#more").html("收起地址>>");
                                    $("#more").addClass("upup");
                                }
                            })

                            // 选择地址（单选，不可取消到无选中）
                            $(".allAdd_content").off('click.orderAddr', '.base').on('click.orderAddr', '.base', function () {
                                $(this).addClass('base_select').siblings('.base').removeClass('base_select');
                            });
                            //控制新增收货地址框的显示隐藏
                            $("#choose").click(function () {
                                $(".modal").show();
                            })
                            $(".cha").click(function () {
                                $(".modal").hide();
                            })
                            $(".user_site").click(function () {
                                $(this).parent().attr("class", "base_select").siblings().attr("class", "base");
                                $(this).hide();
                            })
                            //地址页面添加名称至输入框
                            $(".sp").click(function () {
                                var value = $(this).html();
                                $("#addressName").val(value);
                            })
                            $('.save_recipient').click(function () {
                                orderConfirm.data.addads()
                            })
                        })
                    },
                    error:function(){
                        alert('加载订单失败，请检查网络或重新登录');
                    }
                }
            )
            }
            var token=AuthStorage.getToken();
            var username = AuthStorage.getUser();
            var sku_data = location.search
            console.log(sku_data)
            if(sku_data==''){
                paramenter_url = "?settlement_type=0"
                settlement_type=0
                push_ajax(paramenter_url,settlement_type)
            }else{
                paramenter_url = sku_data+"&settlement_type=1"
                settlement_type=1
                push_ajax(paramenter_url,settlement_type)
            }
        }

window.onload = function () {
    orders();
};

})();
