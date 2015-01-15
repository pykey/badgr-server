var React = require('react');
var ReactPropTypes = React.PropTypes;
var EarnerActions = require('../actions/earner');


var InputGroup = React.createClass({
  propTypes: {
    name: ReactPropTypes.string,
    label: ReactPropTypes.string,
    inputType: ReactPropTypes.string,
    selectOptions: ReactPropTypes.arrayOf(ReactPropTypes.string),
    value: React.PropTypes.string,
    handleChange: ReactPropTypes.func,
    placeholder: ReactPropTypes.string
  },
  classNameForInput: function(){
    var classes = {
      "filebutton": "input-file",
      "textarea": "input-textarea", //wrong. double-check. http://getbootstrap.com/components/#input-groups says you can't use textarea in .input-group
      "select": "input-group-select"
    };
    return classes[this.props.inputType];
  },
  theInput: function(){
    if (this.props.inputType == "filebutton"){
      // TODO: Add accept='image/*' ??
      return ( <input name={this.props.name} value={this.props.value} className={this.classNameForInput()} type="file" onChange={this.props.handleChange} /> );
    }
    else if (this.props.inputType == "text"){
      ( <input name={this.props.name} value={this.props.value} className={this.classNameForInput()} type="text" onChange={this.props.handleChange} /> );
    }
    else if (this.props.inputType == "textarea"){
      return ( <textarea name={this.props.name} value={this.props.value} onChange={this.props.handleChange} /> );
    }
    else if (this.props.inputType == "select") {
      var selectOptions = this.props.selectOptions.map(function(option, index){
        return ( <option value={option} key={this.props.name + '-' + index}>{option}</option>);
      }.bind(this));
      return ( 
        <select name={this.props.name} value={this.props.value} className="input-xlarge" onChange={this.props.handleChange}>
          { selectOptions }
        </select>
      );
    }
  },
  render: function(){
    return (
      <div className="control-group">
        <label className="control-label" htmlFor={this.props.name}>{this.props.label}</label>
        <div className="controls">
          { this.theInput() }
        </div>
      </div>
    )
  }
});


var SubmitButton = React.createClass({
  handleClick: function(e){
    if (!this.props.isDisabled)
      this.props.handleClick(e);
    e.preventDefault();
    e.stopPropagation();
  },
  render: function() {
    return (
      <div className="control-group">
        <label className="control-label sr-only" htmlFor={this.props.name}>{ this.props.label || "Submit" }</label>
        <div className="controls">
          <button name={this.props.name} className="btn btn-primary" onClick={this.handleClick}>{this.props.label || "Submit" }</button>
        </div>
      </div>
    );
  }
});


var EarnerBadgeForm = React.createClass({
  propTypes: {
    action: ReactPropTypes.string,
    recipientIds: ReactPropTypes.arrayOf(ReactPropTypes.string),
    selectedRecipientId: ReactPropTypes.string,
    pk: ReactPropTypes.number,
    earner_description: ReactPropTypes.string,
    image: ReactPropTypes.string, 
  },

  getDefaultProps: function() {
    return {
      formState: "disabled", // "ready", "waiting", "disabled"
      earner_description: "",
      recipientIds: ['none@example.com'],
      action: '/earn/badges'
    };
  },
  getInitialState: function() {
    return {
      recipient_input: this.props.recipientIds[0] || "",
      earner_description: this.props.earner_description 
    };
  },
  handleChange: function(event){
    var field = event.target.name;
    if (field == 'image'){
      var value = event.target.files[0];
    }
    else{
      var value = event.target.value;
    }
    var theChange = {};
    theChange[field] = value;
    this.setState(theChange);
  },


  handleSubmit: function(e){

    var data = {
      recipient_input: this.state.recipient_input,
      earner_description: this.state.earner_description,
    };
    var image = this.state.image;
    if (this.props.pk)
      data['pk'] = this.props.pk;
    EarnerActions.submitEarnerBadgeForm(data, image);

    e.preventDefault(); 
    e.stopPropagation;
  },

  render: function(){
    var isDisabled = (this.props.formState == "disabled");
    var badgeImage = this.props.image ? (<img src={this.props.image} />) : "";
    return (
      <form action={this.props.action} method="POST" className="form-horizontal">
        <fieldset>
          { badgeImage }

          <InputGroup name="image" inputType="filebutton" label="Badge Image" formState={isDisabled} handleChange={this.handleChange} />

          <InputGroup name="earner_description" inputType="textarea" 
            label="Earner Annotation" value={this.state.earner_description} 
            formState={isDisabled}  handleChange={this.handleChange}
            />

          <InputGroup name="recipient_input" 
            inputType="select" selectOptions={this.props.recipientIds} 
            value={this.state.recipient_input} 
            defaultValue={this.props.recipientIds[0]} 
            formState={isDisabled} handleChange={this.handleChange}
          />

          <SubmitButton name="submit" handleClick={this.handleSubmit} formState={isDisabled} />

        </fieldset>
      </form>
    )
  }
});

// Export the Menu class for rendering:
module.exports.EarnerBadgeForm = EarnerBadgeForm;
