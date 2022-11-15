var generated = 0;
var activeRequests = [];
var completedRequest = [];

var apiUrl = "http://127.0.0.1:8073"

// First, checks if it isn't implemented yet.
if (!String.prototype.format) {
  String.prototype.format = function() {
    var args = arguments;
    return this.replace(/{(\d+)}/g, function(match, number) { 
      return typeof args[number] != 'undefined'
        ? args[number]
        : match
      ;
    });
  };
}

function xmlHttpRequestAsync(method, theUrl, callback)
{
  var xmlHttp = new XMLHttpRequest();
  xmlHttp.onreadystatechange = function() {
    if (xmlHttp.readyState == 4 && xmlHttp.status == 200)
    {
      callback(xmlHttp.responseText);
    }
  }
  xmlHttp.open(method, theUrl, true);
  xmlHttp.send(null);
}

function populateSelectCallback(text)
{
  var respJson = JSON.parse(text);

  $("#model-select").find('option').remove();
  respJson['model_names'].forEach(function(currentVal, idx, arr)
  {
    $("#model-select").append($('<option>', {
      value: currentVal,
      text: currentVal
    }));
  })
}

function startGenerateCallback(text)
{
  var respJson = JSON.parse(text);
  var reqDiv = `<div class="req-div" id="{0}-div">
    <p class="req-id" id="{0}-id">Request {0}:</p>
    <p class="req-status" id="{0}-status">Pending...</p>
  </div>`.format(respJson["id"]);
  $("#audio-playback").append(reqDiv)
  activeRequests.push(respJson["id"]);
}

function checkGenerateCallback(text)
{
  var respJson = JSON.parse(text);

  var reqDiv = "#{0}-div".format(respJson["id"]);
  var reqStatus = "#{0}-status".format(respJson["id"]);

  if (respJson["status"] == 1)
  {
    $(reqStatus).remove()

    var reqAudio = `<div class="req-audio-controls" id="{0}-audio-controls">
      <audio controls>
        <source src="{1}" type="audio/wav">
      </audio>
    </div>
    `.format(respJson["id"], respJson["path"]);
    $(reqDiv).append(reqAudio);

    activeRequests = activeRequests.filter(function(f) {return f !== respJson["id"]});
  }
  else if (respJson["status"] == 2)
  {
    $(reqStatus).text("FAILED.");
    activeRequests = activeRequests.filter(function(f) {return f !== respJson["id"]});
  }
}

function checkActiveRequests(text)
{
  for (const i in activeRequests)
  {
    var reqUrl = apiUrl + "/api/v1/tts?request=" + encodeURIComponent(activeRequests[i]);
    xmlHttpRequestAsync("GET", reqUrl, checkGenerateCallback);
  }
}

$(window).on('load', function() {
  var reqUrl = apiUrl + "/api/v1/models";
  xmlHttpRequestAsync("GET", reqUrl, populateSelectCallback);

  $("form").submit(function() { return false; });

  $("#generate-grifflim").on('click', function() {
    var modelName = $("#model-select").val();
    var text = $("input[type=text]#input-text").val();

    if (text)
    {
      var reqUrl = apiUrl + "/api/v1/tts?model=" + encodeURIComponent(modelName) + "&voc=grifflim&text=" + encodeURIComponent(text);
      xmlHttpRequestAsync("GET", reqUrl, startGenerateCallback);
      $("#input-text").val("");
    }
  });

  $("#generate-wavernn").on('click', function() {
    var modelName = $("#model-select").val();
    var text = $("input[type=text]#input-text").val();

    if (text)
    {
      var reqUrl = apiUrl + "/api/v1/tts?model=" + encodeURIComponent(modelName) + "&text=" + encodeURIComponent(text);
      xmlHttpRequestAsync("GET", reqUrl, startGenerateCallback);
      $("#input-text").val("");
    }
  });

  $("#input-text").keypress(function(e)
  {
    if (e.keyCode == 13)
    {
      $("#generate-wavernn").click();
    }
  });

  var intervalId = setInterval(function() { checkActiveRequests(); }, 2500);
});