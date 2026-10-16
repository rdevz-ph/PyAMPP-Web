// PyAMPP Web UI Frontend Engine

const PyAMPP = {
  statusInterval: null,
  installProgressTimer: null,
  isInstalling: false,

  init: function() {
    this.initTheme();
    this.bindEvents();
    this.fetchStatus();
    this.statusInterval = setInterval(() => this.fetchStatus(), 3000);
    this.pollInstallProgress();
  },

  // Dark / Light Mode Toggle
  initTheme: function() {
    const savedTheme = localStorage.getItem('pyampp_theme') || 'light';
    if (savedTheme === 'dark') {
      $('body').addClass('dark-mode');
      $('.main-header').removeClass('navbar-white navbar-light').addClass('navbar-dark');
      $('#darkModeToggle i').removeClass('fa-moon').addClass('fa-sun');
    } else {
      $('body').removeClass('dark-mode');
      $('.main-header').removeClass('navbar-dark').addClass('navbar-white navbar-light');
      $('#darkModeToggle i').removeClass('fa-sun').addClass('fa-moon');
    }

    $('#darkModeToggle').on('click', function(e) {
      e.preventDefault();
      const isDark = $('body').hasClass('dark-mode');
      if (isDark) {
        $('body').removeClass('dark-mode');
        $('.main-header').removeClass('navbar-dark').addClass('navbar-white navbar-light');
        $('#darkModeToggle i').removeClass('fa-sun').addClass('fa-moon');
        localStorage.setItem('pyampp_theme', 'light');
      } else {
        $('body').addClass('dark-mode');
        $('.main-header').removeClass('navbar-white navbar-light').addClass('navbar-dark');
        $('#darkModeToggle i').removeClass('fa-moon').addClass('fa-sun');
        localStorage.setItem('pyampp_theme', 'dark');
      }
    });
  },

  showAlert: function(message, type = 'info', timeout = 4000) {
    const container = $('#alertContainer');
    if (!container.length) return;

    const alertClass = type === 'success' ? 'alert-success' : (type === 'error' ? 'alert-danger' : 'alert-info');
    const iconClass = type === 'success' ? 'fa-check-circle' : (type === 'error' ? 'fa-exclamation-triangle' : 'fa-info-circle');

    const alertHtml = `
      <div class="alert ${alertClass} alert-dismissible fade show shadow-sm" role="alert">
        <i class="fas ${iconClass} mr-2"></i> ${message}
        <button type="button" class="close" data-dismiss="alert" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
    `;

    const el = $(alertHtml).appendTo(container);
    if (timeout > 0) {
      setTimeout(() => {
        el.alert('close');
      }, timeout);
    }
  },

  bindEvents: function() {
    // Global service actions
    $(document).on('click', '[data-service-action]', function(e) {
      e.preventDefault();
      const btn = $(this);
      const service = btn.data('service');
      const action = btn.data('service-action');
      PyAMPP.executeServiceAction(service, action, btn);
    });

    // Native Windows folder picker handler
    $(document).on('click', '.browse-dir-btn', function(e) {
      e.preventDefault();
      const btn = $(this);
      const targetInput = $(btn.data('target'));
      const currentPath = targetInput.val() ? targetInput.val().trim() : '';
      const originalHtml = btn.html();

      btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin mr-1"></i> Browsing...');

      $.ajax({
        url: '/api/config/browse',
        type: 'POST',
        timeout: 120000,
        contentType: 'application/json',
        data: JSON.stringify({ initial_dir: currentPath }),
        success: function(res) {
          if (res && res.success && res.path) {
            let chosen = res.path;
            if (btn.data('strip-bin') || targetInput.attr('id') === 'installDir') {
              if (chosen.toLowerCase().endsWith('\\bin')) {
                chosen = chosen.slice(0, -4);
              } else if (chosen.toLowerCase().endsWith('/bin')) {
                chosen = chosen.slice(0, -4);
              }
            }
            targetInput.val(chosen).trigger('change');
            PyAMPP.showAlert(`Selected: ${chosen}`, 'success', 3000);
          }
        },
        error: function(xhr, status) {
          if (status !== 'timeout') {
            const msg = xhr.responseJSON ? xhr.responseJSON.message : 'Folder selection cancelled or closed.';
            PyAMPP.showAlert(msg, 'info', 2500);
          }
        },
        complete: function() {
          btn.prop('disabled', false).html(originalHtml);
        }
      });
    });

    // Quick open shortcut handler (htdocs, php.ini, httpd.conf, my.ini, etc.)
    $(document).on('click', '.quick-open-item', function(e) {
      e.preventDefault();
      const btn = $(this);
      const target = btn.data('open-target');
      if (!target) return;

      $.ajax({
        url: '/api/open-path',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ target: target }),
        success: function(res) {
          if (res.success) {
            PyAMPP.showAlert(res.message, 'success', 2500);
          } else {
            PyAMPP.showAlert(res.message, 'error');
          }
        },
        error: function(xhr) {
          const msg = xhr.responseJSON ? xhr.responseJSON.message : 'Failed to open requested shortcut.';
          PyAMPP.showAlert(msg, 'error');
        }
      });
    });
  },

  setButtonState: function(selector, isEnabled) {
    const el = $(selector);
    if (!el.length) return;
    if (isEnabled) {
      el.prop('disabled', false).removeAttr('disabled').removeClass('disabled');
      if (el.is('a')) {
        el.removeAttr('tabindex').removeAttr('aria-disabled');
      }
    } else {
      el.prop('disabled', true).attr('disabled', 'disabled').addClass('disabled');
      if (el.is('a')) {
        el.attr('tabindex', '-1').attr('aria-disabled', 'true');
      }
    }
  },

  executeServiceAction: function(service, action, btn) {
    if (btn) btn.prop('disabled', true).attr('disabled', 'disabled').addClass('disabled');
    
    $.ajax({
      url: `/api/service/${service}/${action}`,
      type: 'POST',
      contentType: 'application/json',
      success: function(res) {
        if (res.success) {
          PyAMPP.showAlert(res.message, 'success');
        } else {
          PyAMPP.showAlert(res.message, 'error');
        }
      },
      error: function(xhr) {
        const msg = xhr.responseJSON ? xhr.responseJSON.message : 'Server communication failed.';
        PyAMPP.showAlert(msg, 'error');
      },
      complete: function() {
        // Query status immediately and schedule follow-up checks for OS process/port release
        PyAMPP.fetchStatus();
        setTimeout(() => PyAMPP.fetchStatus(), 600);
        setTimeout(() => PyAMPP.fetchStatus(), 1500);
      }
    });
  },

  fetchStatus: function() {
    const self = this;
    $.getJSON('/api/status', function(data) {
      self.updateDashboardStatus(data);
    });
    // Check if background install started from another tab/page
    if (!self.isInstalling) {
      self.pollInstallProgress();
    }
  },

  pollInstallProgress: function(forceImmediate = false) {
    const self = this;
    $.getJSON('/api/component/progress', function(res) {
      self.handleInstallProgressResponse(res);
    }).fail(function() {
      if (self.isInstalling && !self.installProgressTimer) {
        self.installProgressTimer = setInterval(() => self.pollInstallProgress(), 2000);
      }
    });
  },

  handleInstallProgressResponse: function(res) {
    if (!res) return;
    const self = this;

    if (res.in_progress) {
      self.isInstalling = true;
      const pct = res.percent !== undefined && res.percent >= 0 ? res.percent : 0;

      // Update AdminLTE 3 top navbar notification widget
      $('#globalNavInstallProgress').show();
      $('#navInstallIcon').attr('class', 'fas fa-spinner fa-spin text-primary');
      $('#navInstallBadge')
        .attr('class', 'badge badge-primary navbar-badge')
        .text(`${pct}%`);
      $('#navInstallPctBadge')
        .attr('class', 'badge badge-primary')
        .text(`${pct}%`);
      $('#navInstallPercentText').text(`${pct}%`);
      $('#navInstallTitle').text(res.title || 'Component Setup');
      $('#navInstallMsg').text(res.message || 'Please wait...');
      $('#navInstallProgressBar')
        .css('width', `${pct}%`)
        .removeClass('bg-danger bg-success')
        .addClass('bg-primary progress-bar-striped progress-bar-animated');

      // Update wizard page if currently active
      if ($('#progressCard').length) {
        $('#progressCard').removeClass('d-none');
        $('#progressTitle').text(res.title || 'Installing Components...');
        $('#progressDetail').text(res.message || 'Please wait...');
        $('#progressBar')
          .css('width', `${pct}%`)
          .removeClass('bg-danger bg-success')
          .addClass('bg-primary progress-bar-striped progress-bar-animated');
        $('.install-single-btn, #installAllBtn').prop('disabled', true);
      }

      // Ensure rapid polling while in progress
      if (!self.installProgressTimer) {
        self.installProgressTimer = setInterval(() => self.pollInstallProgress(), 1000);
      }
    } else {
      // Installation is NOT in progress
      if (self.installProgressTimer) {
        clearInterval(self.installProgressTimer);
        self.installProgressTimer = null;
      }

      if (self.isInstalling) {
        // Just finished
        self.isInstalling = false;
        if (res.error) {
          self.showAlert(`Installation failed: ${res.error}`, 'error');
          $('#navInstallIcon').attr('class', 'fas fa-exclamation-triangle text-danger');
          $('#navInstallBadge').attr('class', 'badge badge-danger navbar-badge').text('Error');
          $('#navInstallPctBadge').attr('class', 'badge badge-danger').text('Error');
          $('#navInstallProgressBar').removeClass('bg-primary bg-success').addClass('bg-danger');
          $('#navInstallMsg').text(res.error);

          if ($('#progressCard').length) {
            $('#progressTitle').text('Installation Failed');
            $('#progressDetail').text(res.error);
            $('#progressBar').removeClass('bg-primary bg-success').addClass('bg-danger');
            $('.install-single-btn, #installAllBtn').prop('disabled', false);
          }
          if (typeof window.checkWizardComponentStatus === 'function') {
            window.checkWizardComponentStatus();
          }
          setTimeout(() => {
            if (!self.isInstalling) $('#globalNavInstallProgress').fadeOut();
          }, 8000);
        } else {
          self.showAlert('Component installation completed successfully.', 'success');
          $('#navInstallIcon').attr('class', 'fas fa-check text-success');
          $('#navInstallBadge').attr('class', 'badge badge-success navbar-badge').text('Done');
          $('#navInstallPctBadge').attr('class', 'badge badge-success').text('100%');
          $('#navInstallProgressBar')
            .css('width', '100%')
            .removeClass('bg-primary bg-danger')
            .addClass('bg-success');
          $('#navInstallMsg').text('Completed successfully.');
          $('#navInstallPercentText').text('100%');

          if ($('#progressCard').length) {
            $('#progressTitle').text('Installation Complete');
            $('#progressDetail').text('All requested components were installed successfully.');
            $('#progressBar')
              .css('width', '100%')
              .removeClass('bg-primary bg-danger')
              .addClass('bg-success');
            $('.install-single-btn, #installAllBtn').prop('disabled', false);
            if ($('#wizardFinishCard').length) {
              $('#wizardFinishCard').removeClass('d-none').hide().fadeIn();
            }
          }
          if (typeof window.checkWizardComponentStatus === 'function') {
            window.checkWizardComponentStatus();
          }
          self.fetchStatus();
          setTimeout(() => {
            if (!self.isInstalling) {
              $('#globalNavInstallProgress').fadeOut();
              if ($('#progressCard').length) {
                $('#progressCard').fadeOut(function() {
                  $(this).addClass('d-none').show();
                });
              }
            }
          }, 6000);
        }
      } else {
        // Was already not installing, keep widget hidden
        $('#globalNavInstallProgress').hide();
      }
    }
  },

  updateDashboardStatus: function(data) {
    if (!data) return;

    const apacheRunning = Boolean(data.apache && data.apache.running);
    const mysqlRunning = Boolean(data.mysql && data.mysql.running);

    // Top navbar quick links
    if (data.apache && data.apache.port) {
      $('#topHtdocsBtn').attr('href', `http://localhost:${data.apache.port}`);
      $('#topPmaBtn').attr('href', `http://localhost:${data.apache.port}/phpmyadmin`);
    }

    // Update Apache Cards/Badges & Buttons
    if (data.apache) {
      const badge = $('#apacheStatusBadge');
      if (badge.length) {
        badge.attr('class', `status-badge ${apacheRunning ? 'running' : 'stopped'}`);
        badge.html(`<i class="fas fa-circle mr-1" style="font-size:0.6rem;"></i> ${apacheRunning ? 'RUNNING' : 'STOPPED'}`);
      }
      $('#apachePortDisplay').text(data.apache.port || '-');
      $('#apachePidDisplay').text(data.apache.pid || '-');
      $('#apacheMemoryDisplay').text(data.apache.memory || '-');

      // Start is disabled when already running; Stop/Restart enabled when running
      PyAMPP.setButtonState('#apacheStartBtn, [data-service="apache"][data-service-action="start"]', !apacheRunning);
      PyAMPP.setButtonState('#apacheStopBtn, [data-service="apache"][data-service-action="stop"]', apacheRunning);
      PyAMPP.setButtonState('#apacheRestartBtn, [data-service="apache"][data-service-action="restart"]', apacheRunning);
      PyAMPP.setButtonState('#apacheOpenLink', apacheRunning);
    }

    // Update MySQL Cards/Badges & Buttons
    if (data.mysql) {
      const badge = $('#mysqlStatusBadge');
      if (badge.length) {
        badge.attr('class', `status-badge ${mysqlRunning ? 'running' : 'stopped'}`);
        badge.html(`<i class="fas fa-circle mr-1" style="font-size:0.6rem;"></i> ${mysqlRunning ? 'RUNNING' : 'STOPPED'}`);
      }
      $('#mysqlPortDisplay').text(data.mysql.port || '-');
      $('#mysqlPidDisplay').text(data.mysql.pid || '-');
      $('#mysqlMemoryDisplay').text(data.mysql.memory || '-');

      // Start is disabled when already running; Stop/Restart enabled when running
      PyAMPP.setButtonState('#mysqlStartBtn, [data-service="mysql"][data-service-action="start"]', !mysqlRunning);
      PyAMPP.setButtonState('#mysqlStopBtn, [data-service="mysql"][data-service-action="stop"]', mysqlRunning);
      PyAMPP.setButtonState('#mysqlRestartBtn, [data-service="mysql"][data-service-action="restart"]', mysqlRunning);
      PyAMPP.setButtonState('#mysqlOpenPmaLink', mysqlRunning);
    }

    // Update Global Controls
    const canStartAll = !(apacheRunning && mysqlRunning);
    const canStopAll = apacheRunning || mysqlRunning;
    const canRestartAll = apacheRunning || mysqlRunning;

    PyAMPP.setButtonState('#globalStartAllBtn, [data-service="all"][data-service-action="start"]', canStartAll);
    PyAMPP.setButtonState('#globalStopAllBtn, [data-service="all"][data-service-action="stop"]', canStopAll);
    PyAMPP.setButtonState('#globalRestartAllBtn, [data-service="all"][data-service-action="restart"]', canRestartAll);

    // Update Installed Versions
    if (data.versions) {
      $('#installedPhpVer').text(data.versions.php || 'Not installed');
      $('#installedApacheVer').text(data.versions.apache || 'Not installed');
      $('#installedMysqlVer').text(data.versions.mysql || 'Not installed');
      $('#installedPmaVer').text(data.versions.phpmyadmin || 'Not installed');
    }
  }
};

$(document).ready(function() {
  PyAMPP.init();
});
