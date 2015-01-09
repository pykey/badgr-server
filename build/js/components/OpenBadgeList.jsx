var React = require('react');
var OpenBadge = require('../components/BadgeDisplay.jsx').OpenBadge;
var APIStore = require('../stores/APIStore');

var OpenBadgeList = React.createClass({
  /*
  this.props.badgeList = [
    { 
      badge: {
        full_badge_object: { assertion, badgeclass, issuerorg },
        image, pk, recipient_input
      }, 
      earner: "username" 
    }
  ]
  */
  getDefaultProps: function() {
    return {
      badgeList: [],
      activeBadgeId: null
    };
  },
  render: function(){
    var badgesInList = this.props.badgeList.map(function(item, i){
      return (
        <OpenBadge 
          key={"key-" + item.badge.pk}
          pk={item.badge.pk}
          display={ this.props.activeBadgeId == item.badge.pk ? "detail" : "thumbnail" } 
          badge={ item.badge.full_badge_object }
          earner={ item.badge.recipient_input }
          setActiveBadgeId={ this.props.setActiveBadgeId }
        />
      );
    }.bind(this));
    return (
      <div className="open-badge-list">
        { badgesInList }
      </div>
    );
  }
});

// Export the Menu class for rendering:
module.exports = OpenBadgeList;